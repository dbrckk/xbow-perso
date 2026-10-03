import copy

import pytest

from app.recovery_attestation import (
    RecoveryAttestationError,
    build_recovery_attestation,
    load_and_verify_recovery_attestation,
    verify_recovery_attestation,
    write_recovery_attestation,
)


def _backup(*, valid=True, signed=True):
    return {
        "valid": valid,
        "manifest_signature_valid": signed,
        "artifacts": {
            "postgres": {"valid": valid},
            "redis": {"valid": valid},
            "vault": {"valid": valid},
        },
    }


def _queue(*, safe=True):
    return {
        "safe_to_resume": safe,
        "assessment_truncated": False,
        "jobs_total": 3,
        "jobs_assessed": 3,
        "issues_total": 0 if safe else 1,
        "issues_by_severity": {
            "critical": 0 if safe else 1,
            "warning": 0,
        },
    }


def _audits(*, valid=True, legacy=False):
    return [
        {
            "campaign": {
                "valid": valid,
                "checked": 4,
                "legacy_unsealed": 1 if legacy else 0,
            },
            "worker": {
                "valid": valid,
                "checked": 2,
                "sealed_outcomes": 2,
                "legacy_unsealed": ["legacy-job"] if legacy else [],
            },
        }
    ]


def _key(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "attestation-test-key")


def test_recovery_attestation_ready_roundtrip(monkeypatch):
    _key(monkeypatch)

    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
        issued_at="2026-10-03T16:00:00+00:00",
    )

    assert attestation["schema"] == "recovery-attestation-v1"
    assert attestation["decision"] == "READY"
    assert attestation["ready_to_restore"] is True
    assert attestation["block_reasons"] == []
    assert attestation["review_reasons"] == []
    assert attestation["contains_targets"] is False
    assert attestation["contains_payloads"] is False
    assert attestation["contains_worker_identities"] is False
    assert attestation["contains_secrets"] is False
    assert attestation["contains_backup_contents"] is False
    assert len(attestation["attestation_digest"]) == 64
    assert len(attestation["signature"]) == 64

    verified = verify_recovery_attestation(attestation)
    assert verified["valid"] is True
    assert verified["decision"] == "READY"
    assert verified["ready_to_restore"] is True


def test_recovery_attestation_reviews_unsigned_or_legacy_state(monkeypatch):
    _key(monkeypatch)

    attestation = build_recovery_attestation(
        backup_verification=_backup(signed=False),
        queue_assessment=_queue(),
        campaign_audits=_audits(legacy=True),
    )

    assert attestation["decision"] == "REVIEW"
    assert attestation["ready_to_restore"] is False
    assert set(attestation["review_reasons"]) == {
        "backup_manifest_not_authenticated",
        "legacy_unsealed_audit_events",
    }
    assert verify_recovery_attestation(attestation)["valid"] is True


def test_recovery_attestation_blocks_invalid_prerequisites_but_remains_signed(monkeypatch):
    _key(monkeypatch)

    attestation = build_recovery_attestation(
        backup_verification=_backup(valid=False),
        queue_assessment=_queue(safe=False),
        campaign_audits=_audits(valid=False),
    )

    assert attestation["decision"] == "BLOCK"
    assert attestation["ready_to_restore"] is False
    assert set(attestation["block_reasons"]) == {
        "backup_verification_invalid",
        "queue_not_safe_to_resume",
        "audit_chain_invalid",
    }
    assert verify_recovery_attestation(attestation)["valid"] is True


def test_recovery_attestation_rejects_tampering(monkeypatch):
    _key(monkeypatch)
    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
    )
    tampered = copy.deepcopy(attestation)
    tampered["queue"]["jobs_total"] = 999

    result = verify_recovery_attestation(tampered)

    assert result["valid"] is False
    assert result["reason"] == "recovery attestation digest mismatch"


def test_recovery_attestation_rejects_privacy_invariant_tampering(monkeypatch):
    _key(monkeypatch)
    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
    )
    attestation["contains_targets"] = True

    result = verify_recovery_attestation(attestation)

    assert result["valid"] is False
    assert result["reason"] == "recovery attestation privacy invariant mismatch"


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


def test_recovery_attestation_file_roundtrip_is_private(monkeypatch, tmp_path):
    _key(monkeypatch)
    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
    )
    destination = tmp_path / "recovery-attestation.json"

    write_recovery_attestation(attestation, str(destination))
    verified = load_and_verify_recovery_attestation(str(destination))

    assert verified["valid"] is True
    assert oct(destination.stat().st_mode & 0o777) == "0o600"


def test_recovery_attestation_preserves_unowned_temporary_file(monkeypatch, tmp_path):
    _key(monkeypatch)
    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
    )
    destination = tmp_path / "recovery-attestation.json"
    temporary = tmp_path / "recovery-attestation.json.tmp"
    temporary.write_bytes(b"other-writer")

    with pytest.raises(RecoveryAttestationError, match="write failed"):
        write_recovery_attestation(attestation, str(destination))

    assert temporary.read_bytes() == b"other-writer"
    assert not destination.exists()


def test_recovery_attestation_writer_rejects_symlink(monkeypatch, tmp_path):
    _key(monkeypatch)
    attestation = build_recovery_attestation(
        backup_verification=_backup(),
        queue_assessment=_queue(),
        campaign_audits=_audits(),
    )
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "attestation.json"
    link.symlink_to(real)

    with pytest.raises(RecoveryAttestationError, match="must not be a symlink"):
        write_recovery_attestation(attestation, str(link))
