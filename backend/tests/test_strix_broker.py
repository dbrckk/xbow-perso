import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.main import Campaign, ProgramRules, TargetInput
from app.strix_broker import (
    BrokerAdmissionRequest,
    BrokerCommandTicketRequest,
    BrokerContractDocument,
    BrokerHttpRequest,
    BrokerHttpResponse,
    admit,
    healthz,
    issue_command_ticket,
    readyz,
    request_http,
)
from app.strix_broker_client import StrixBrokerClientError
from app.strix_execution_contract import build_strix_execution_contract
from app.strix_runner_exec_ticket import verify_strix_runner_exec_ticket


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


ADMISSION_SECRET = "broker-runner-admission-secret-at-least-32-bytes"


def _signed_contract(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "broker-fixture-secret")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")
    return BrokerContractDocument.model_validate(contract.to_dict())


def _configure_broker_keys(monkeypatch):
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")
    monkeypatch.setenv(
        "XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY",
        ADMISSION_SECRET,
    )


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


def test_broker_readiness_requires_runner_admission_key(monkeypatch):
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")
    monkeypatch.delenv(
        "XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY",
        raising=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        readyz()

    assert exc_info.value.status_code == 503
    assert "admission signing key" in str(exc_info.value.detail)


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


def test_broker_health_reports_read_only_proxy_when_enabled(monkeypatch):
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")
    monkeypatch.setenv(
        "XBOW_STRIX_BROKER_ENABLE_READONLY_EGRESS",
        "true",
    )

    result = healthz()

    assert result["ready"] is True
    assert result["mode"] == "read_only_http_proxy"
    assert result["egress_enabled"] is True
    assert result["allowed_http_methods"] == ["GET", "HEAD"]


def test_broker_issues_runner_ticket_only_after_command_admission(monkeypatch):
    contract = _signed_contract(monkeypatch)
    _configure_broker_keys(monkeypatch)
    argv = [
        "curl",
        "-fsS",
        "http://127.0.0.1:48080/graphql",
    ]

    result = issue_command_ticket(
        BrokerCommandTicketRequest(
            contract=contract,
            session_id="sess-1",
            request_id="req-1",
            profile="bootstrap-v1",
            argv=argv,
            timeout_seconds=10.0,
        )
    )

    assert result.allowed is True
    assert result.mode == "ticket_issuer_only"
    assert result.network_io_performed is False
    assert result.process_execution_performed is False
    verified = verify_strix_runner_exec_ticket(
        result.ticket.model_dump(mode="json"),
        session_id="sess-1",
        request_id="req-1",
        argv=argv,
        timeout_seconds=10.0,
        verification_secret=ADMISSION_SECRET,
    )
    assert verified.contract_hash == contract.contract_hash
    assert verified.profile == "bootstrap-v1"
    assert verified.active_execution_enabled is False


def test_broker_command_ticket_rejects_wrong_contract_key(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "different-secret")
    monkeypatch.setenv(
        "XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY",
        ADMISSION_SECRET,
    )

    with pytest.raises(HTTPException) as exc_info:
        issue_command_ticket(
            BrokerCommandTicketRequest(
                contract=contract,
                session_id="sess-1",
                request_id="req-1",
                profile="bootstrap-v1",
                argv=["curl", "-I", "http://127.0.0.1:48080/"],
                timeout_seconds=10.0,
            )
        )

    assert exc_info.value.status_code == 403


@pytest.mark.parametrize(
    ("profile", "argv"),
    (
        ("bootstrap-v1", ["sh", "-lc", "printf ok"]),
        ("bootstrap-v1", ["nuclei", "-version"]),
    ),
)
def test_broker_command_ticket_rejects_unreviewed_command(monkeypatch, profile, argv):
    contract = _signed_contract(monkeypatch)
    _configure_broker_keys(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        issue_command_ticket(
            BrokerCommandTicketRequest(
                contract=contract,
                session_id="sess-1",
                request_id="req-1",
                profile=profile,
                argv=argv,
                timeout_seconds=10.0,
            )
        )

    assert exc_info.value.status_code == 403
    assert "command admission rejected" in str(exc_info.value.detail).lower()


def test_broker_command_ticket_requires_signing_key(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")
    monkeypatch.delenv(
        "XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY",
        raising=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        issue_command_ticket(
            BrokerCommandTicketRequest(
                contract=contract,
                session_id="sess-1",
                request_id="req-1",
                profile="bootstrap-v1",
                argv=["curl", "-I", "http://127.0.0.1:48080/"],
                timeout_seconds=10.0,
            )
        )

    assert exc_info.value.status_code == 503


def test_broker_request_path_is_disabled_by_default(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")
    monkeypatch.delenv(
        "XBOW_STRIX_BROKER_ENABLE_READONLY_EGRESS",
        raising=False,
    )
    monkeypatch.setattr(
        "app.strix_broker.forward_read_only_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("egress client must not run")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        request_http(
            BrokerHttpRequest(
                contract=contract,
                target="https://app.example.test/",
                requested_rps=1.0,
            )
        )

    assert exc_info.value.status_code == 503


def test_broker_revalidates_contract_before_forwarding(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "wrong-secret")
    monkeypatch.setenv(
        "XBOW_STRIX_BROKER_ENABLE_READONLY_EGRESS",
        "true",
    )
    monkeypatch.setattr(
        "app.strix_broker.forward_read_only_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("egress client must not run")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        request_http(
            BrokerHttpRequest(
                contract=contract,
                target="https://app.example.test/",
                requested_rps=1.0,
            )
        )

    assert exc_info.value.status_code == 403


def test_broker_forwards_only_after_local_admission(monkeypatch):
    contract = _signed_contract(monkeypatch)
    monkeypatch.setenv("XBOW_STRIX_BROKER_HMAC_KEY", "broker-fixture-secret")
    monkeypatch.setenv(
        "XBOW_STRIX_BROKER_ENABLE_READONLY_EGRESS",
        "true",
    )
    captured = {}

    def fake_forward(request):
        captured["request"] = request
        return BrokerHttpResponse(
            status_code=200,
            reason="OK",
            headers=[],
            body_base64="b2s=",
            body_bytes=2,
            truncated=False,
            contract_hash=request.contract.contract_hash,
            host="app.example.test",
            method=request.method,
        )

    monkeypatch.setattr(
        "app.strix_broker.forward_read_only_request",
        fake_forward,
    )
    request = BrokerHttpRequest(
        contract=contract,
        target="https://app.example.test/profile",
        requested_rps=1.0,
        method="HEAD",
    )

    result = request_http(request)

    assert captured["request"] is request
    assert result.status_code == 200
    assert result.host == "app.example.test"
    assert result.mode == "read_only_http"
    assert result.egress_enforced is True


def test_broker_readiness_requires_egress_when_proxy_enabled(monkeypatch):
    _configure_broker_keys(monkeypatch)
    monkeypatch.setenv(
        "XBOW_STRIX_BROKER_ENABLE_READONLY_EGRESS",
        "true",
    )
    monkeypatch.setattr(
        "app.strix_broker.check_egress_ready",
        lambda: (_ for _ in ()).throw(
            StrixBrokerClientError(
                "fixture unavailable",
                status_code=503,
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        readyz()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Strix read-only egress is not ready"


def test_broker_readiness_checks_egress_when_proxy_enabled(monkeypatch):
    _configure_broker_keys(monkeypatch)
    monkeypatch.setenv(
        "XBOW_STRIX_BROKER_ENABLE_READONLY_EGRESS",
        "true",
    )
    called = {"count": 0}

    def ready():
        called["count"] += 1

    monkeypatch.setattr("app.strix_broker.check_egress_ready", ready)

    result = readyz()

    assert called["count"] == 1
    assert result["status"] == "ready"
    assert result["egress_enabled"] is True
