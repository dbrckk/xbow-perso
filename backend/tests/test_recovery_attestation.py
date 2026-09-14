import copy

import pytest

from app.recovery_attestation import (
    RecoveryAttestationError,
    build_recovery_attestation,
    verify_recovery_attestation,
)


def _backup():
    return {
        "valid": True,
        "manifest_signature_valid": True,
        "artifacts": {
            "postgres": {"valid": True},
            "redis": {"valid": True},
            "vault": {"valid": True},
        },
    }


def _queue():
    return {
        "safe_to_resume": True,
        "storage": "sqlite",
        "jobs_total": 4,
        "issues_total": 0,
    }


def _audits():
    return [
        {
            "campaign": {"valid": True, "checked": 3},
            "worker": {"valid": True, "checked": 2},
            "queue": {"valid": True, "events": 5},
        }
    ]


def test_recovery_attestation_roundtrip(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "attestation-key")

    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        issued_at="2026-09-14T13:00:00+00:00",
    )

    assert attestation["schema"] == "recovery-attestation-v1"
    assert attestation["contains_targets"] is False
    assert attestation["contains_payloads"] is False
    assert attestation["contains_secrets"] is False
    assert attestation["contains_backup_contents"] is False
    assert attestation["queue"]["automatic_mutation"] is False
    assert attestation["queue"]["automatic_requeue"] is False
    assert attestation["queue"]["automatic_job_creation"] is False
    assert len(attestation["attestation_digest"]) == 64
    assert len(attestation["signature"]) == 64
    assert verify_recovery_attestation(attestation)["valid"] is True


def test_recovery_attestation_rejects_tampering(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "attestation-key")

    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        issued_at="2026-09-14T13:00:00+00:00",
    )
    tampered = copy.deepcopy(attestation)
    tampered["queue"]["jobs_total"] = 999

    result = verify_recovery_attestation(tampered)

    assert result["valid"] is False
    assert result["reason"] == "recovery attestation digest mismatch"


def test_recovery_attestation_rejects_invalid_backup(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "attestation-key")
    backup = _backup()
    backup["valid"] = False

    with pytest.raises(
        RecoveryAttestationError,
        match="backup verification must be valid",
    ):
        build_recovery_attestation(
            backup_verification=backup,
            queue_assessment=_queue(),
            campaign_audits=_audits(),
        )


def test_recovery_attestation_rejects_unsafe_queue(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "attestation-key")
    queue = _queue()
    queue["safe_to_resume"] = False

    with pytest.raises(
        RecoveryAttestationError,
        match="queue recovery assessment must be safe",
    ):
        build_recovery_attestation(
            backup_verification=_backup(),
            queue_assessment=queue,
            campaign_audits=_audits(),
        )


def test_recovery_attestation_rejects_invalid_campaign_audit(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "attestation-key")
    audits = _audits()
    audits[0]["worker"]["valid"] = False

    with pytest.raises(
        RecoveryAttestationError,
        match="campaign audit verification must be valid",
    ):
        build_recovery_attestation(
            backup_verification=_backup(),
            queue_assessment=_queue(),
            campaign_audits=audits,
        )


def test_recovery_attestation_requires_signing_key(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)

    with pytest.raises(
        RecoveryAttestationError,
        match="signing key is unavailable",
    ):
        build_recovery_attestation(
            backup_verification=_backup(),
            queue_assessment=_queue(),
            campaign_audits=_audits(),
        )



def test_recovery_attestation_file_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "attestation-key")
    from app.recovery_attestation import (
        load_and_verify_recovery_attestation,
        write_recovery_attestation,
    )

    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        issued_at="2026-09-14T13:00:00+00:00",
    )
    destination = tmp_path / "recovery-attestation.json"

    write_recovery_attestation(attestation, str(destination))
    result = load_and_verify_recovery_attestation(str(destination))

    assert result["valid"] is True
    assert oct(destination.stat().st_mode & 0o777) == "0o600"


def test_recovery_attestation_writer_rejects_symlink(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "attestation-key")
    from app.recovery_attestation import write_recovery_attestation

    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
    )
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "attestation.json"
    link.symlink_to(real)

    with pytest.raises(
        RecoveryAttestationError,
        match="must not be a symlink",
    ):
        write_recovery_attestation(attestation, str(link))
