from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

from .main import Campaign
from .pentagi_adapter import PentagiFlowPlan, PentagiPolicyError


class PentagiAdmissionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiAdmissionDecision:
    allowed: bool
    reasons: tuple[str, ...]
    campaign_id: str
    target: str
    max_requests_per_second: float
    policy_fingerprint: str


def _strict_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise PentagiAdmissionError(f"{name} must be a boolean")


def _bounded_admission_rps() -> float:
    raw = (os.getenv("XBOW_PENTAGI_MAX_ADMISSION_RPS") or "2.0").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise PentagiAdmissionError(
            "XBOW_PENTAGI_MAX_ADMISSION_RPS must be numeric"
        ) from exc
    if not 0.1 <= value <= 20.0:
        raise PentagiAdmissionError(
            "XBOW_PENTAGI_MAX_ADMISSION_RPS must be between 0.1 and 20"
        )
    return value


def _policy_fingerprint(campaign: Campaign, plan: PentagiFlowPlan) -> str:
    rules = campaign.target.rules
    payload = {
        "campaign_id": campaign.id,
        "target": plan.target,
        "allowed_targets": sorted(str(item) for item in rules.allowed_targets),
        "denied_targets": sorted(str(item) for item in rules.denied_targets),
        "max_requests_per_second": float(rules.max_requests_per_second),
        "automated_scanning": bool(rules.automated_scanning),
        "destructive_testing": bool(rules.destructive_testing),
        "denial_of_service": bool(rules.denial_of_service),
        "social_engineering": bool(rules.social_engineering),
        "credential_attacks": bool(rules.credential_attacks),
        "endpoint": plan.endpoint,
        "provider": plan.model_provider,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def evaluate_pentagi_admission(
    campaign: Campaign,
    plan: PentagiFlowPlan,
) -> PentagiAdmissionDecision:
    """Evaluate whether a PentAGI plan may ever reach an execution transport.

    The current adapter intentionally has no enforceable egress/rate-limit transport,
    so admission remains denied even when an operator enables PentAGI. This function
    centralizes that invariant so a future transport cannot accidentally bypass it.
    """

    if plan.target != str(campaign.target.primary_url):
        raise PentagiPolicyError("PentAGI plan target does not match campaign target")

    reasons: list[str] = []
    enabled = _strict_bool_env("XBOW_ENABLE_PENTAGI", False)
    active_scans = _strict_bool_env("XBOW_ENABLE_ACTIVE_SCANS", False)
    dry_run = _strict_bool_env("DRY_RUN", True)
    admission_cap = _bounded_admission_rps()
    campaign_rps = float(campaign.target.rules.max_requests_per_second)

    if not enabled:
        reasons.append("pentagi_disabled")
    if not active_scans:
        reasons.append("active_scans_disabled")
    if dry_run:
        reasons.append("global_dry_run")
    if campaign_rps > admission_cap:
        reasons.append("campaign_rps_exceeds_admission_cap")
    if plan.dry_run:
        reasons.append("plan_is_dry_run")
    if not plan.execution_supported:
        reasons.append("execution_transport_not_enforceable")

    return PentagiAdmissionDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
        campaign_id=campaign.id,
        target=plan.target,
        max_requests_per_second=campaign_rps,
        policy_fingerprint=_policy_fingerprint(campaign, plan),
    )


def require_pentagi_admission(
    campaign: Campaign,
    plan: PentagiFlowPlan,
) -> PentagiAdmissionDecision:
    decision = evaluate_pentagi_admission(campaign, plan)
    if not decision.allowed:
        raise PentagiAdmissionError(
            "PentAGI execution admission denied: " + ",".join(decision.reasons)
        )
    return decision
