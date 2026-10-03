from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .campaign_audit import verify_campaign_event_chain
from .secret_vault import SecretVaultError, resolve_secret
from .worker_audit import verify_worker_audit_chain

ATTESTATION_SCHEMA = "recovery-attestation-v1"
_MAX_ATTESTATION_BYTES = 1024 * 1024


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


def collect_recovery_campaign_audits(storage_backend) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for campaign in storage_backend.list_campaigns():
        events = campaign.get("events") or []
        if not isinstance(events, list):
            audits.append(
                {
                    "campaign": {
                        "valid": False,
                        "checked": 0,
                        "legacy_unsealed": 0,
                        "reason": "campaign audit events are invalid",
                    },
                    "worker": {
                        "valid": False,
                        "checked": 0,
                        "sealed_outcomes": 0,
                        "legacy_unsealed": [],
                        "reason": "campaign audit events are invalid",
                    },
                }
            )
            continue
        try:
            worker = verify_worker_audit_chain(events)
        except SecretVaultError:
            worker = {
                "valid": False,
                "checked": 0,
                "sealed_outcomes": 0,
                "legacy_unsealed": [],
                "reason": "verification key unavailable",
            }
        audits.append(
            {
                "campaign": verify_campaign_event_chain(events),
                "worker": worker,
            }
        )
    return audits


def _summarize_campaign_audits(
    audits: list[dict[str, Any]],
) -> dict[str, Any]:
    invalid_campaign_chains = 0
    invalid_worker_chains = 0
    campaign_events_checked = 0
    worker_outcomes_checked = 0
    legacy_campaign_events = 0
    legacy_worker_outcomes = 0

    for item in audits:
        campaign = item.get("campaign") if isinstance(item, dict) else {}
        worker = item.get("worker") if isinstance(item, dict) else {}
        campaign = campaign if isinstance(campaign, dict) else {}
        worker = worker if isinstance(worker, dict) else {}

        if campaign.get("valid") is not True:
            invalid_campaign_chains += 1
        if worker.get("valid") is not True:
            invalid_worker_chains += 1

        campaign_events_checked += int(campaign.get("checked") or 0)
        worker_outcomes_checked += int(worker.get("checked") or 0)
        legacy_campaign_events += int(campaign.get("legacy_unsealed") or 0)

        legacy_worker = worker.get("legacy_unsealed") or []
        if isinstance(legacy_worker, list):
            legacy_worker_outcomes += len(legacy_worker)
        else:
            legacy_worker_outcomes += int(bool(legacy_worker))

    return {
        "campaigns_checked": len(audits),
        "invalid_campaign_chains": invalid_campaign_chains,
        "invalid_worker_chains": invalid_worker_chains,
        "campaign_events_checked": campaign_events_checked,
        "worker_outcomes_checked": worker_outcomes_checked,
        "legacy_campaign_events": legacy_campaign_events,
        "legacy_worker_outcomes": legacy_worker_outcomes,
        "valid": invalid_campaign_chains == 0 and invalid_worker_chains == 0,
        "fully_sealed": legacy_campaign_events == 0 and legacy_worker_outcomes == 0,
    }


def build_recovery_attestation(
    *,
    backup_verification: dict[str, Any],
    queue_assessment: dict[str, Any],
    campaign_audits: list[dict[str, Any]],
    issued_at: str | None = None,
) -> dict[str, Any]:
    campaign_summary = _summarize_campaign_audits(campaign_audits)

    backup_valid = backup_verification.get("valid") is True
    manifest_signed = backup_verification.get("manifest_signature_valid") is True
    queue_safe = queue_assessment.get("safe_to_resume") is True
    queue_complete = queue_assessment.get("assessment_truncated") is not True
    audits_valid = campaign_summary["valid"]

    block_reasons: list[str] = []
    review_reasons: list[str] = []
    if not backup_valid:
        block_reasons.append("backup_verification_invalid")
    if not queue_safe:
        block_reasons.append("queue_not_safe_to_resume")
    if not queue_complete:
        block_reasons.append("queue_assessment_truncated")
    if not audits_valid:
        block_reasons.append("audit_chain_invalid")

    if not manifest_signed and backup_valid:
        review_reasons.append("backup_manifest_not_authenticated")
    if not campaign_summary["fully_sealed"] and audits_valid:
        review_reasons.append("legacy_unsealed_audit_events")

    if block_reasons:
        decision = "BLOCK"
    elif review_reasons:
        decision = "REVIEW"
    else:
        decision = "READY"

    artifacts = backup_verification.get("artifacts") or {}
    artifact_validity = {
        str(kind): bool(value.get("valid"))
        for kind, value in sorted(artifacts.items())
        if isinstance(value, dict)
    }
    queue_severity = queue_assessment.get("issues_by_severity") or {}

    payload = {
        "schema": ATTESTATION_SCHEMA,
        "issued_at": issued_at or datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "ready_to_restore": decision == "READY",
        "block_reasons": block_reasons,
        "review_reasons": review_reasons,
        "backup": {
            "valid": backup_valid,
            "manifest_signature_valid": backup_verification.get(
                "manifest_signature_valid"
            ),
            "artifacts_valid": artifact_validity,
        },
        "queue": {
            "safe_to_resume": queue_safe,
            "assessment_truncated": bool(
                queue_assessment.get("assessment_truncated")
            ),
            "jobs_total": int(queue_assessment.get("jobs_total") or 0),
            "jobs_assessed": int(queue_assessment.get("jobs_assessed") or 0),
            "issues_total": int(queue_assessment.get("issues_total") or 0),
            "critical_issues": int(queue_severity.get("critical") or 0),
            "warning_issues": int(queue_severity.get("warning") or 0),
            "automatic_mutation": False,
            "automatic_requeue": False,
            "automatic_job_creation": False,
        },
        "campaign_audits": campaign_summary,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_worker_identities": False,
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
        return {"valid": False, "reason": "unsupported recovery attestation schema"}
    if attestation.get("signature_alg") != "hmac-sha256":
        return {
            "valid": False,
            "reason": "unsupported recovery attestation signature algorithm",
        }

    decision = attestation.get("decision")
    if decision not in {"READY", "REVIEW", "BLOCK"}:
        return {"valid": False, "reason": "invalid recovery attestation decision"}
    if bool(attestation.get("ready_to_restore")) != (decision == "READY"):
        return {"valid": False, "reason": "recovery readiness invariant mismatch"}
    for key in (
        "contains_targets",
        "contains_payloads",
        "contains_worker_identities",
        "contains_secrets",
        "contains_backup_contents",
    ):
        if attestation.get(key) is not False:
            return {"valid": False, "reason": "recovery attestation privacy invariant mismatch"}

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
        return {"valid": False, "reason": "recovery attestation digest mismatch"}

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
        return {"valid": False, "reason": "recovery attestation signature mismatch"}

    return {
        "valid": True,
        "reason": None,
        "schema": ATTESTATION_SCHEMA,
        "decision": decision,
        "ready_to_restore": decision == "READY",
        "attestation_digest": expected_digest,
    }


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
    if len(encoded.encode("utf-8")) > _MAX_ATTESTATION_BYTES:
        raise RecoveryAttestationError("recovery attestation exceeds size limit")

    owns_tmp = False
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            owns_tmp = True
            os.chmod(tmp, 0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        owns_tmp = False
        os.chmod(path, 0o600)
    except OSError as exc:
        if owns_tmp:
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
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > _MAX_ATTESTATION_BYTES
        ):
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
