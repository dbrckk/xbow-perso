from dataclasses import replace

import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.strix_execution_contract import (
    STRIX_EXECUTION_CONTRACT_SCHEMA,
    StrixExecutionContractError,
    authorize_strix_contract_request,
    build_strix_execution_contract,
    verify_strix_execution_contract,
)


def _campaign(*, rps=1.5, denied=None):
    return Campaign(
        id="campaign-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test", "api.example.test"],
                denied_targets=denied or ["admin.example.test"],
                max_requests_per_second=rps,
            ),
        ),
    )


def test_contract_is_deterministic_and_binds_policy_and_job(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-contract-key")
    campaign = _campaign()

    first = build_strix_execution_contract(campaign, job_id="job-1")
    second = build_strix_execution_contract(campaign, job_id="job-1")

    assert first == second
    assert first.schema == STRIX_EXECUTION_CONTRACT_SCHEMA
    assert first.engine == "strix"
    assert first.contract_hash
    assert first.signature_alg == "hmac-sha256"
    assert first.signature
    assert first.allowed_targets == ("*.example.test", "api.example.test")
    assert first.denied_targets == ("admin.example.test",)
    assert first.direct_egress_allowed is False
    assert first.host_container_socket_allowed is False
    assert first.independent_validation_required is True

    verify_strix_execution_contract(first, campaign, job_id="job-1")


def test_contract_summary_is_redacted(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-contract-key")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")

    summary = contract.redacted_summary()

    assert summary["authenticated"] is True
    assert summary["contract_hash"] == contract.contract_hash
    assert "allowed_targets" not in summary
    assert "denied_targets" not in summary
    assert "primary_target" not in summary
    assert "signature" not in summary


def test_unsigned_contract_can_be_previewed_but_not_used_by_runtime(monkeypatch):
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")

    assert contract.signature is None
    assert contract.redacted_summary()["authenticated"] is False
    verify_strix_execution_contract(contract, _campaign(), job_id="job-1")

    with pytest.raises(StrixExecutionContractError, match="signature is required"):
        authorize_strix_contract_request(
            contract,
            target="https://app.example.test/profile",
            requested_rps=1.0,
        )


def test_signed_contract_authorizes_only_in_scope_rate_bounded_requests(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-contract-key")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")

    authorized = authorize_strix_contract_request(
        contract,
        target="https://api.example.test/profile?id=1",
        requested_rps=1.0,
    )

    assert authorized.contract_hash == contract.contract_hash
    assert authorized.host == "api.example.test"
    assert authorized.max_requests_per_second == 1.0

    with pytest.raises(StrixExecutionContractError, match="outside scope"):
        authorize_strix_contract_request(
            contract,
            target="https://evil.invalid/profile",
            requested_rps=1.0,
        )

    with pytest.raises(StrixExecutionContractError, match="outside scope"):
        authorize_strix_contract_request(
            contract,
            target="https://admin.example.test/profile",
            requested_rps=1.0,
        )

    with pytest.raises(StrixExecutionContractError, match="exceeds contract cap"):
        authorize_strix_contract_request(
            contract,
            target="https://app.example.test/profile",
            requested_rps=2.0,
        )


def test_contract_tampering_fails_before_request_authorization(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-contract-key")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")
    forged = replace(contract, max_requests_per_second=20.0)

    with pytest.raises(StrixExecutionContractError, match="hash mismatch"):
        authorize_strix_contract_request(
            forged,
            target="https://app.example.test/",
            requested_rps=10.0,
        )


def test_policy_change_invalidates_existing_contract(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-contract-key")
    campaign = _campaign()
    contract = build_strix_execution_contract(campaign, job_id="job-1")

    campaign.target.rules.max_requests_per_second = 1.0

    with pytest.raises(StrixExecutionContractError, match="policy changed"):
        verify_strix_execution_contract(contract, campaign, job_id="job-1")


def test_job_change_invalidates_existing_contract(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-contract-key")
    campaign = _campaign()
    contract = build_strix_execution_contract(campaign, job_id="job-1")

    with pytest.raises(StrixExecutionContractError, match="job mismatch"):
        verify_strix_execution_contract(contract, campaign, job_id="job-2")


@pytest.mark.parametrize(
    "flag",
    (
        "destructive_testing",
        "denial_of_service",
        "social_engineering",
        "credential_attacks",
    ),
)
def test_unsafe_campaign_flags_block_contract_issuance(monkeypatch, flag):
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    campaign = _campaign()
    setattr(campaign.target.rules, flag, True)

    with pytest.raises(StrixExecutionContractError, match=flag):
        build_strix_execution_contract(campaign, job_id="job-1")


def test_automated_scanning_must_remain_enabled(monkeypatch):
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    campaign = _campaign()
    campaign.target.rules.automated_scanning = False

    with pytest.raises(
        StrixExecutionContractError,
        match="automated_scanning_disabled",
    ):
        build_strix_execution_contract(campaign, job_id="job-1")
