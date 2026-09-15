from __future__ import annotations

import hashlib
import json
from typing import Any

from .campaign_audit import verify_campaign_event_chain


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _binding_fingerprint(
    *,
    policy_snapshot_sha256: str,
    campaign_policy_fingerprint: str,
) -> str:
    return canonical_json_sha256(
        {
            "provider": "hackerone",
            "mode": "conservative",
            "policy_snapshot_sha256": policy_snapshot_sha256,
            "campaign_policy_fingerprint": campaign_policy_fingerprint,
        }
    )


def verify_hackerone_campaign_binding(
    campaign: Any,
    *,
    current_policy_fingerprint: str,
) -> dict[str, Any]:
    binding_events = [
        event
        for event in campaign.events
        if isinstance(event, dict) and event.get("type") == "hackerone_policy_bound"
    ]
    if not binding_events:
        return {
            "required": False,
            "valid": True,
            "reasons": [],
            "binding_fingerprint": None,
        }

    reasons: list[str] = []
    if len(binding_events) != 1:
        reasons.append("binding_event_count_invalid")

    audit = verify_campaign_event_chain(campaign.events)
    if not audit.get("valid") or int(audit.get("legacy_unsealed") or 0) != 0:
        reasons.append("campaign_audit_chain_invalid")

    binding = binding_events[-1]
    if binding.get("provider") != "hackerone":
        reasons.append("binding_provider_invalid")
    if binding.get("mode") != "conservative":
        reasons.append("binding_mode_invalid")

    snapshot = binding.get("policy_snapshot")
    if not isinstance(snapshot, dict):
        reasons.append("policy_snapshot_missing")
        snapshot = {}

    declared_snapshot_hash = str(binding.get("policy_snapshot_sha256") or "")
    actual_snapshot_hash = canonical_json_sha256(snapshot)
    if declared_snapshot_hash != actual_snapshot_hash:
        reasons.append("policy_snapshot_sha256_mismatch")

    if snapshot.get("safe_harbor_confirmed") is not True:
        reasons.append("safe_harbor_not_confirmed")
    if snapshot.get("automated_scanning") is not True:
        reasons.append("automated_scanning_not_authorized")
    if snapshot.get("test_account_required") is not False:
        reasons.append("test_account_workflow_not_supported")
    if snapshot.get("test_account_constraints") not in {"", None}:
        reasons.append("test_account_constraints_not_supported")
    restrictions = snapshot.get("additional_restrictions")
    if restrictions not in ([], (), None):
        reasons.append("additional_restrictions_require_manual_enforcement")

    declared_policy_fingerprint = str(binding.get("campaign_policy_fingerprint") or "")
    if declared_policy_fingerprint != current_policy_fingerprint:
        reasons.append("campaign_policy_fingerprint_mismatch")

    expected_binding_fingerprint = _binding_fingerprint(
        policy_snapshot_sha256=actual_snapshot_hash,
        campaign_policy_fingerprint=current_policy_fingerprint,
    )
    declared_binding_fingerprint = str(binding.get("binding_fingerprint") or "")
    if declared_binding_fingerprint != expected_binding_fingerprint:
        reasons.append("binding_fingerprint_mismatch")

    return {
        "required": True,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
        "binding_fingerprint": declared_binding_fingerprint or None,
    }
