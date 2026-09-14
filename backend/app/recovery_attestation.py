from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .campaign_audit import verify_campaign_event_chain
from .worker_audit import verify_worker_audit_chain

from .secret_vault import SecretVaultError, resolve_secret


ATTESTATION_SCHEMA = "recovery-attestation-v1"


class RecoveryAttestationError(RuntimeError):
    pass


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _signing_secret() -> str:
    try:
        secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
    except SecretVaultError as exc:
        raise RecoveryAttestationError(
            "recovery attestation signing key is unavailable"
        ) from exc
    if not secret:
        raise RecoveryAttestationError(
            "recovery attestation signing key is unavailable"
        )
    return secret


def _normalize_campaign_audits(
    audits: list[dict[str, Any]],
) -> dict[str, Any]:
    invalid = 0
    campaign_events_checked = 0
    worker_outcomes_checked = 0
    queue_events_checked = 0

    for item in audits:
        campaign = item.get("campaign") or {}
        worker = item.get("worker") or {}
        queue = item.get("queue") or {}
        valid = (
            bool(campaign.get("valid"))
            and bool(worker.get("valid"))
            and bool(queue.get("valid"))
        )
        if not valid:
            invalid += 1
        campaign_events_checked += int(campaign.get("checked") or 0)
        worker_outcomes_checked += int(worker.get("checked") or 0)
        queue_events_checked += int(queue.get("events") or 0)

    return {
        "campaigns_checked": len(audits),
        "invalid_campaigns": invalid,
        "campaign_events_checked": campaign_events_checked,
        "worker_outcomes_checked": worker_outcomes_checked,
        "queue_events_checked": queue_events_checked,
        "valid": invalid == 0,
    }


def build_recovery_attestation(
    *,
    backup_verification: dict[str, Any],
    queue_assessment: dict[str, Any],
    campaign_audits: list[dict[str, Any]],
    issued_at: str | None = None,
) -> dict[str, Any]:
    campaign_summary = _normalize_campaign_audits(campaign_audits)
    backup_valid = bool(backup_verification.get("valid"))
    queue_valid = bool(queue_assessment.get("safe_to_resume"))

    if not backup_valid:
        raise RecoveryAttestationError(
            "backup verification must be valid before attestation"
        )
    if not queue_valid:
        raise RecoveryAttestationError(
            "queue recovery assessment must be safe before attestation"
        )
    if not campaign_summary["valid"]:
        raise RecoveryAttestationError(
            "campaign audit verification must be valid before attestation"
        )

    timestamp = issued_at or datetime.now(timezone.utc).isoformat()
    payload = {
        "schema": ATTESTATION_SCHEMA,
        "issued_at": timestamp,
        "backup": {
            "valid": True,
            "manifest_signature_valid": backup_verification.get(
                "manifest_signature_valid"
            ),
            "artifacts_valid": {
                str(kind): bool((value or {}).get("valid"))
                for kind, value in sorted(
                    (backup_verification.get("artifacts") or {}).items()
                )
            },
        },
        "queue": {
            "safe_to_resume": True,
            "storage": str(queue_assessment.get("storage") or "unknown"),
            "jobs_total": int(queue_assessment.get("jobs_total") or 0),
            "issues_total": int(queue_assessment.get("issues_total") or 0),
            "automatic_mutation": False,
            "automatic_requeue": False,
            "automatic_job_creation": False,
        },
        "campaign_audits": campaign_summary,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
        "contains_backup_contents": False,
    }

    canonical = _canonical_payload(payload)
    digest = hashlib.sha256(canonical).hexdigest()
    signature = hmac.new(
        _signing_secret().encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()

    return {
        **payload,
        "attestation_digest": digest,
        "signature_alg": "hmac-sha256",
        "signature": signature,
    }


def verify_recovery_attestation(attestation: dict[str, Any]) -> dict[str, Any]:
    if attestation.get("schema") != ATTESTATION_SCHEMA:
        return {
            "valid": False,
            "reason": "unsupported recovery attestation schema",
        }
    if attestation.get("signature_alg") != "hmac-sha256":
        return {
            "valid": False,
            "reason": "unsupported recovery attestation signature algorithm",
        }

    payload = {
        key: value
        for key, value in attestation.items()
        if key not in {"attestation_digest", "signature_alg", "signature"}
    }
    canonical = _canonical_payload(payload)
    expected_digest = hashlib.sha256(canonical).hexdigest()
    if not hmac.compare_digest(
        str(attestation.get("attestation_digest") or ""),
        expected_digest,
    ):
        return {
            "valid": False,
            "reason": "recovery attestation digest mismatch",
        }

    try:
        secret = _signing_secret()
    except RecoveryAttestationError:
        return {
            "valid": False,
            "reason": "recovery attestation verification key unavailable",
        }

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(
        str(attestation.get("signature") or ""),
        expected_signature,
    ):
        return {
            "valid": False,
            "reason": "recovery attestation signature mismatch",
        }

    return {
        "valid": True,
        "reason": None,
        "attestation_digest": expected_digest,
        "schema": ATTESTATION_SCHEMA,
    }



def collect_recovery_campaign_audits(storage_backend, queue_backend) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for campaign in storage_backend.list_campaigns():
        campaign_id = str(campaign.get("id") or "")
        if not campaign_id:
            raise RecoveryAttestationError("campaign without identifier cannot be attested")
        events = campaign.get("events") or []
        if not isinstance(events, list):
            raise RecoveryAttestationError("campaign audit events are invalid")
        audits.append(
            {
                "campaign": verify_campaign_event_chain(events),
                "worker": verify_worker_audit_chain(events),
                "queue": queue_backend.campaign_transition_audit(campaign_id),
            }
        )
    return audits


def write_recovery_attestation(
    attestation: dict[str, Any],
    destination: str,
) -> None:
    path = Path(destination)
    if path.is_symlink():
        raise RecoveryAttestationError(
            "recovery attestation path must not be a symlink"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    encoded = json.dumps(attestation, sort_keys=True, indent=2)
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            os.chmod(tmp, 0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise RecoveryAttestationError(
            "recovery attestation write failed"
        ) from exc


def load_and_verify_recovery_attestation(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise OSError("unsafe attestation")
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryAttestationError(
            "recovery attestation file is invalid"
        ) from exc
    if not isinstance(document, dict):
        raise RecoveryAttestationError(
            "recovery attestation file is invalid"
        )
    return verify_recovery_attestation(document)
