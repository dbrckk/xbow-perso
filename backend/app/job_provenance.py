from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

from .hackerone_binding import verify_hackerone_campaign_binding


PROVENANCE_SCHEMA = "job-provenance-v1"


class JobProvenanceError(RuntimeError):
    pass


def stable_policy_snapshot(campaign: Any) -> dict[str, Any]:
    """Return deterministic policy state relevant to worker admission."""
    rules = campaign.target.rules
    host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
    return {
        "campaign_id": str(campaign.id),
        "target": str(campaign.target.primary_url),
        "host": host,
        "authorization_reference": str(rules.authorization_reference),
        "allowed_targets": sorted(str(item) for item in rules.allowed_targets),
        "denied_targets": sorted(str(item) for item in rules.denied_targets),
        "max_requests_per_second": float(rules.max_requests_per_second),
        "automated_scanning": bool(rules.automated_scanning),
        "destructive_testing": bool(rules.destructive_testing),
        "denial_of_service": bool(rules.denial_of_service),
        "social_engineering": bool(rules.social_engineering),
        "credential_attacks": bool(rules.credential_attacks),
    }


def policy_snapshot_fingerprint(campaign: Any) -> str:
    encoded = json.dumps(
        stable_policy_snapshot(campaign),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_job_provenance(
    campaign: Any,
    *,
    job_kind: str,
    action: str,
) -> dict[str, Any]:
    snapshot = stable_policy_snapshot(campaign)
    policy_fingerprint = policy_snapshot_fingerprint(campaign)
    binding = verify_hackerone_campaign_binding(
        campaign,
        current_policy_fingerprint=policy_fingerprint,
    )
    if binding["required"] and not binding["valid"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne policy binding invalid",
                "reasons": binding["reasons"],
            },
        )
    return {
        "schema": PROVENANCE_SCHEMA,
        "campaign_id": str(campaign.id),
        "job_kind": str(job_kind),
        "action": str(action),
        "scope_host": snapshot["host"],
        "policy_fingerprint": policy_fingerprint,
        "request_rate_limit": snapshot["max_requests_per_second"],
    }


def attach_job_provenance(
    payload: dict[str, Any],
    campaign: Any,
    *,
    job_kind: str,
    action: str,
) -> dict[str, Any]:
    if "_provenance" in payload:
        raise JobProvenanceError("job payload already contains provenance metadata")
    return {
        **payload,
        "_provenance": build_job_provenance(
            campaign,
            job_kind=job_kind,
            action=action,
        ),
    }


def verify_job_provenance(job: dict[str, Any], campaign: Any) -> dict[str, Any]:
    payload = job.get("payload")
    provenance = payload.get("_provenance") if isinstance(payload, dict) else None
    reasons: list[str] = []

    if not isinstance(provenance, dict):
        return {
            "valid": False,
            "reasons": ["provenance_missing"],
            "policy_fingerprint": None,
            "expected_policy_fingerprint": policy_snapshot_fingerprint(campaign),
        }

    if provenance.get("schema") != PROVENANCE_SCHEMA:
        reasons.append("unsupported_provenance_schema")
    if str(provenance.get("campaign_id") or "") != str(campaign.id):
        reasons.append("campaign_id_mismatch")
    if str(provenance.get("job_kind") or "") != str(job.get("kind") or ""):
        reasons.append("job_kind_mismatch")

    expected = policy_snapshot_fingerprint(campaign)
    actual = str(provenance.get("policy_fingerprint") or "")
    if actual != expected:
        reasons.append("policy_fingerprint_mismatch")

    snapshot = stable_policy_snapshot(campaign)
    if str(provenance.get("scope_host") or "").lower() != snapshot["host"]:
        reasons.append("scope_host_mismatch")

    try:
        declared_rps = float(provenance.get("request_rate_limit"))
    except (TypeError, ValueError):
        reasons.append("invalid_request_rate_limit")
    else:
        if declared_rps != float(snapshot["max_requests_per_second"]):
            reasons.append("request_rate_limit_mismatch")

    return {
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
        "policy_fingerprint": actual or None,
        "expected_policy_fingerprint": expected,
    }


def require_job_provenance(job: dict[str, Any], campaign: Any) -> dict[str, Any]:
    verification = verify_job_provenance(job, campaign)
    if not verification["valid"]:
        raise JobProvenanceError(
            "job provenance rejected: " + ",".join(verification["reasons"])
        )
    return verification


GOVERNED_JOB_KINDS = frozenset(
    {
        "strix_scan",
        "nuclei_scan",
        "recon_task",
        "browser_flow",
        "independent_validation",
        "report",
    }
)


def provenance_required_for_job_kind(job_kind: str) -> bool:
    return str(job_kind) in GOVERNED_JOB_KINDS
