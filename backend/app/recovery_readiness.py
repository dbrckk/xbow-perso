from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from .deployment_preflight import build_deployment_preflight
from .recovery_attestation import (
    RecoveryAttestationError,
    collect_recovery_campaign_audits,
    load_and_verify_recovery_attestation,
)


RECOVERY_STATES = ("BLOCK", "REVIEW", "READY")


def build_recovery_readiness(
    *,
    preflight: dict[str, Any],
    queue_assessment: dict[str, Any],
    campaign_audits: list[dict[str, Any]],
    attestation_verification: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    review: list[str] = []

    if preflight.get("status") == "error":
        blockers.append("deployment_preflight_error")
    elif preflight.get("status") == "warning":
        review.append("deployment_preflight_warning")

    provenance = preflight.get("job_provenance") or {}
    if not bool(provenance.get("configuration_valid", True)):
        blockers.append("job_provenance_configuration_invalid")
    if bool(provenance.get("legacy_unprovenanced_jobs_enabled")):
        review.append("legacy_unprovenanced_jobs_enabled")

    if not bool(queue_assessment.get("safe_to_resume")):
        blockers.append("queue_recovery_not_safe")

    invalid_campaigns = 0
    for item in campaign_audits:
        campaign = item.get("campaign") or {}
        worker = item.get("worker") or {}
        queue = item.get("queue") or {}
        if not (
            bool(campaign.get("valid"))
            and bool(worker.get("valid"))
            and bool(queue.get("valid"))
        ):
            invalid_campaigns += 1
    if invalid_campaigns:
        blockers.append("campaign_audit_invalid")

    if attestation_verification is None:
        review.append("signed_recovery_attestation_missing")
    elif not bool(attestation_verification.get("valid")):
        blockers.append("signed_recovery_attestation_invalid")

    if blockers:
        decision = "BLOCK"
    elif review:
        decision = "REVIEW"
    else:
        decision = "READY"

    return {
        "decision": decision,
        "blockers": sorted(set(blockers)),
        "review_reasons": sorted(set(review)),
        "checks": {
            "preflight_status": preflight.get("status"),
            "queue_safe_to_resume": bool(queue_assessment.get("safe_to_resume")),
            "campaigns_checked": len(campaign_audits),
            "invalid_campaigns": invalid_campaigns,
            "attestation_present": attestation_verification is not None,
            "attestation_valid": (
                bool(attestation_verification.get("valid"))
                if attestation_verification is not None
                else None
            ),
        },
        "workers_may_resume": decision == "READY",
        "automatic_worker_start": False,
        "automatic_mutation": False,
        "read_only": True,
    }


def current_recovery_readiness(
    storage_backend,
    queue_backend,
    *,
    dependencies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preflight = build_deployment_preflight(dependencies)
    queue_assessment = queue_backend.recovery_assessment()
    campaign_audits = collect_recovery_campaign_audits(
        storage_backend,
        queue_backend,
    )

    attestation_verification = None
    attestation_path = (os.getenv("XBOW_RECOVERY_ATTESTATION_PATH") or "").strip()
    if attestation_path:
        try:
            attestation_verification = load_and_verify_recovery_attestation(
                attestation_path
            )
        except RecoveryAttestationError as exc:
            attestation_verification = {
                "valid": False,
                "reason": str(exc),
            }

    return build_recovery_readiness(
        preflight=preflight,
        queue_assessment=queue_assessment,
        campaign_audits=campaign_audits,
        attestation_verification=attestation_verification,
    )



def readiness_snapshot_document(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": str(result.get("decision") or "BLOCK"),
        "blockers": sorted(str(item) for item in result.get("blockers") or []),
        "review_reasons": sorted(
            str(item) for item in result.get("review_reasons") or []
        ),
        "checks": dict(result.get("checks") or {}),
        "workers_may_resume": bool(result.get("workers_may_resume")),
        "automatic_worker_start": False,
        "automatic_mutation": False,
    }


def readiness_snapshot_fingerprint(result: dict[str, Any]) -> str:
    document = readiness_snapshot_document(result)
    encoded = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def record_recovery_readiness(storage_backend, result: dict[str, Any]) -> dict[str, Any]:
    document = readiness_snapshot_document(result)
    fingerprint = readiness_snapshot_fingerprint(result)
    snapshot = storage_backend.put_recovery_readiness_snapshot(
        fingerprint,
        document["decision"],
        document,
    )
    return {
        **result,
        "snapshot_fingerprint": fingerprint,
        "snapshot_created_at": snapshot.get("created_at"),
    }


def recovery_readiness_history(storage_backend, *, limit: int = 100) -> dict[str, Any]:
    snapshots = storage_backend.list_recovery_readiness_snapshots(limit=limit)
    transitions: list[dict[str, Any]] = []
    chronological = list(reversed(snapshots))
    previous = None
    for item in chronological:
        decision = str(item.get("decision") or "")
        if previous is not None and decision != previous["decision"]:
            transitions.append(
                {
                    "from": previous["decision"],
                    "to": decision,
                    "at": item.get("created_at"),
                    "fingerprint": item.get("fingerprint"),
                    "ready_to_block": (
                        previous["decision"] == "READY"
                        and decision == "BLOCK"
                    ),
                }
            )
        previous = {
            "decision": decision,
            "created_at": item.get("created_at"),
        }

    return {
        "snapshots": snapshots,
        "transitions": list(reversed(transitions)),
        "latest_decision": (
            str(snapshots[0].get("decision")) if snapshots else None
        ),
        "ready_to_block_regressions": sum(
            bool(item["ready_to_block"]) for item in transitions
        ),
        "read_only": True,
        "aggregate_only": True,
    }
