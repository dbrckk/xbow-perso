import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.main import Campaign, ProgramRules, TargetInput
from app.strix_broker import (
    BrokerAdmissionRequest,
    BrokerContractDocument,
    admit,
    healthz,
    readyz,
)
from app.strix_execution_contract import build_strix_execution_contract


def _campaign():
    return Campaign(
        id="broker-campaign",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
                max_requests_per_second=1.5,
            ),
        ),
    )


def _signed_contract(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "broker-fixture-secret")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")
    return BrokerContractDocument.model_validate(contract.to_dict())


def test_broker_health_is_explicitly_admission_only(monkeypatch):
    monkeypatch.delenv("XBOW_STRIX_BROKER_HMAC_KEY", raising=False)

    result = healthz()

    assert result["status"] == "ok"
    assert result["ready"] is False
    assert result["mode"] == "admission_only"
    assert result["egress_enabled"] is False
    assert result["network_io_performed"] is False
    assert result["contract_schema"] == "strix-execution-contract-v1"


def test_broker_readiness_requires_verification_key(monkeypatch):
    monkeypatch.delenv("XBOW_STRIX_BROKER_HMAC_KEY", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        readyz()

    assert exc_info.value.status_code == 503


def test_broker_admits_signed_in_scope_request_without_egress(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")

    result = admit(
        BrokerAdmissionRequest(
            contract=contract,
            target="https://api.example.test/profile?id=1",
            requested_rps=1.0,
        )
    )

    assert result.allowed is True
    assert result.host == "api.example.test"
    assert result.max_requests_per_second == 1.0
    assert result.mode == "admission_only"
    assert result.egress_enabled is False
    assert result.network_io_performed is False


def test_broker_rejects_wrong_verification_key(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "different-secret")

    with pytest.raises(HTTPException) as exc_info:
        admit(
            BrokerAdmissionRequest(
                contract=contract,
                target="https://app.example.test/",
                requested_rps=1.0,
            )
        )

    assert exc_info.value.status_code == 403
    assert "signature mismatch" in str(exc_info.value.detail)


def test_broker_rejects_out_of_scope_and_denied_hosts(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")

    for target in (
        "https://evil.invalid/",
        "https://admin.example.test/",
    ):
        with pytest.raises(HTTPException) as exc_info:
            admit(
                BrokerAdmissionRequest(
                    contract=contract,
                    target=target,
                    requested_rps=1.0,
                )
            )
        assert exc_info.value.status_code == 403


def test_broker_rejects_rate_above_signed_contract(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")

    with pytest.raises(HTTPException) as exc_info:
        admit(
            BrokerAdmissionRequest(
                contract=contract,
                target="https://app.example.test/",
                requested_rps=2.0,
            )
        )

    assert exc_info.value.status_code == 403
    assert "exceeds contract cap" in str(exc_info.value.detail)


def test_broker_contract_model_forbids_unsafe_runtime_invariants(monkeypatch):
    contract = _signed_contract(monkeypatch)
    payload = contract.model_dump()
    payload["direct_egress_allowed"] = True

    with pytest.raises(ValidationError):
        BrokerContractDocument.model_validate(payload)
