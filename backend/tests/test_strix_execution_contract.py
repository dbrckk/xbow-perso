from dataclasses import replace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.main import Campaign, ProgramRules, TargetInput
from app.strix_execution_contract import (
    STRIX_EXECUTION_CONTRACT_SCHEMA,
    StrixExecutionContractError,
    authorize_strix_contract_request,
    build_strix_execution_contract,
    verify_strix_execution_contract,
)





@pytest.fixture(autouse=True)
def _clear_ed25519_contract_keys(monkeypatch):
    monkeypatch.delenv(
        "XBOW_STRIX_CONTRACT_SIGNATURE_ALG",
        raising=False,
    )
    monkeypatch.delenv(
        "XBOW_STRIX_CONTRACT_ED25519_PRIVATE_KEY",
        raising=False,
    )
    monkeypatch.delenv(
        "XBOW_STRIX_CONTRACT_ED25519_PUBLIC_KEY",
        raising=False,
    )


def _ed25519_keypair(seed: int = 0) -> tuple[str, str]:
    private_bytes = bytes((seed + index) % 256 for index in range(32))
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_bytes.hex(), public_bytes.hex()


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





def test_runtime_can_verify_with_explicit_broker_secret(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-contract-key")
    contract = build_strix_execution_contract(_campaign(), job_id="job-1")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)

    authorized = authorize_strix_contract_request(
        contract,
        target="https://app.example.test/profile",
        requested_rps=1.0,
        verification_secret="fixture-contract-key",
    )

    assert authorized.host == "app.example.test"

    with pytest.raises(StrixExecutionContractError, match="signature mismatch"):
        authorize_strix_contract_request(
            contract,
            target="https://app.example.test/profile",
            requested_rps=1.0,
            verification_secret="wrong-key",
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



def test_ed25519_contract_verifies_with_public_key_only(monkeypatch):
    private_key, public_key = _ed25519_keypair()
    monkeypatch.setenv("XBOW_STRIX_CONTRACT_SIGNATURE_ALG", "ed25519")
    monkeypatch.setenv(
        "XBOW_STRIX_CONTRACT_ED25519_PRIVATE_KEY",
        private_key,
    )
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fallback-hmac-key")

    contract = build_strix_execution_contract(_campaign(), job_id="job-ed")

    assert contract.signature_alg == "ed25519"
    assert contract.signature is not None
    assert len(contract.signature) == 128

    monkeypatch.delenv(
        "XBOW_STRIX_CONTRACT_ED25519_PRIVATE_KEY",
        raising=False,
    )
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")

    authorized = authorize_strix_contract_request(
        contract,
        target="https://api.example.test/profile",
        requested_rps=1.0,
        verification_public_key=public_key,
    )

    assert authorized.contract_hash == contract.contract_hash
    assert authorized.host == "api.example.test"


def test_ed25519_contract_rejects_wrong_public_key(monkeypatch):
    private_key, _public_key = _ed25519_keypair()
    _, wrong_public = _ed25519_keypair(seed=64)
    monkeypatch.setenv("XBOW_STRIX_CONTRACT_SIGNATURE_ALG", "ed25519")
    monkeypatch.setenv(
        "XBOW_STRIX_CONTRACT_ED25519_PRIVATE_KEY",
        private_key,
    )
    contract = build_strix_execution_contract(_campaign(), job_id="job-ed")

    monkeypatch.delenv(
        "XBOW_STRIX_CONTRACT_ED25519_PRIVATE_KEY",
        raising=False,
    )
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")

    with pytest.raises(StrixExecutionContractError, match="signature mismatch"):
        authorize_strix_contract_request(
            contract,
            target="https://app.example.test/",
            requested_rps=1.0,
            verification_public_key=wrong_public,
        )


def test_ed25519_contract_rejects_malformed_private_key(monkeypatch):
    monkeypatch.setenv("XBOW_STRIX_CONTRACT_SIGNATURE_ALG", "ed25519")
    monkeypatch.setenv(
        "XBOW_STRIX_CONTRACT_ED25519_PRIVATE_KEY",
        "not-a-valid-key",
    )

    with pytest.raises(StrixExecutionContractError, match="private key"):
        build_strix_execution_contract(_campaign(), job_id="job-ed")


def test_hmac_contract_remains_supported_without_ed25519_key(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-contract-key")

    contract = build_strix_execution_contract(_campaign(), job_id="job-hmac")

    assert contract.signature_alg == "hmac-sha256"
    assert contract.signature is not None
    assert len(contract.signature) == 64
