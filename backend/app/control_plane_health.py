from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class HealthComponent:
    name: str
    score: int
    state: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def _state(score: int) -> str:
    if score >= 90:
        return "HEALTHY"
    if score >= 70:
        return "DEGRADED"
    return "BLOCKED"


def _bounded_score(value: int) -> int:
    return max(0, min(100, int(value)))


def build_control_plane_health(dashboard: dict[str, Any]) -> dict[str, Any]:
    summary = dashboard.get("summary") or {}
    recovery = dashboard.get("recovery") or {}
    queue = dashboard.get("queue_integrity") or {}

    critical_alerts = int(summary.get("critical_alerts") or 0)
    warning_alerts = int(summary.get("warning_alerts") or 0)
    failed_jobs = int(summary.get("failed_jobs") or 0)
    pending_outbox = int(summary.get("pending_outbox_total") or 0)

    # Governance: starts from 100 and penalizes operational policy/governance warnings.
    governance_reasons: list[str] = []
    governance_score = 100
    if warning_alerts:
        governance_score -= min(20, warning_alerts * 5)
        governance_reasons.append("operational_warnings")
    if critical_alerts:
        governance_score -= min(40, critical_alerts * 10)
        governance_reasons.append("critical_alerts_present")
    if dashboard.get("health") == "BLOCKED":
        governance_score = min(governance_score, 60)
        governance_reasons.append("platform_blocked")

    # Queue integrity.
    queue_reasons: list[str] = []
    queue_score = 100
    if queue.get("audit_valid") is False:
        queue_score = 0
        queue_reasons.append("queue_transition_audit_invalid")
    invalid_jobs = int(queue.get("audit_invalid_jobs") or 0)
    if invalid_jobs:
        queue_score -= min(60, invalid_jobs * 15)
        queue_reasons.append("invalid_queue_jobs")
    if failed_jobs:
        queue_score -= min(30, failed_jobs * 5)
        queue_reasons.append("failed_jobs")

    # Validation: infer platform-level health from alerts/reasons already aggregated.
    validation_reasons: list[str] = []
    validation_score = 100
    dashboard_reasons = set(dashboard.get("blocked_reasons") or []) | set(
        dashboard.get("degraded_reasons") or []
    )
    if "critical_operational_alert" in dashboard_reasons:
        validation_score -= 15
        validation_reasons.append("critical_operational_alert")
    if "failed_jobs" in dashboard_reasons:
        validation_score -= 10
        validation_reasons.append("failed_jobs_affect_validation_pipeline")

    # Recovery.
    recovery_reasons: list[str] = []
    decision = recovery.get("latest_decision")
    if decision == "READY":
        recovery_score = 100
    elif decision == "REVIEW":
        recovery_score = 70
        recovery_reasons.append("operator_review_required")
    elif decision == "BLOCK":
        recovery_score = 0
        recovery_reasons.append("recovery_blocked")
    else:
        recovery_score = 60
        recovery_reasons.append("recovery_state_unknown")
    regressions = int(recovery.get("ready_to_block_regressions") or 0)
    if regressions:
        recovery_score = min(recovery_score, 40)
        recovery_reasons.append("ready_to_block_regression")

    # Storage / durability signal.
    storage_reasons: list[str] = []
    storage_score = 100
    if queue.get("storage") in {None, "unknown"}:
        storage_score -= 25
        storage_reasons.append("queue_storage_unknown")
    if queue.get("audit_valid") is False:
        storage_score -= 40
        storage_reasons.append("durability_audit_invalid")
    if pending_outbox:
        storage_score -= min(25, pending_outbox * 2)
        storage_reasons.append("pending_outbox")

    # Reporting / submission pipeline health.
    reporting_reasons: list[str] = []
    reporting_score = 100
    if failed_jobs:
        reporting_score -= min(30, failed_jobs * 5)
        reporting_reasons.append("failed_jobs")
    if pending_outbox:
        reporting_score -= min(30, pending_outbox * 2)
        reporting_reasons.append("pending_outbox")
    if critical_alerts:
        reporting_score -= min(20, critical_alerts * 5)
        reporting_reasons.append("critical_alerts_present")

    components = {
        "governance": HealthComponent(
            "governance",
            _bounded_score(governance_score),
            _state(_bounded_score(governance_score)),
            tuple(sorted(set(governance_reasons))),
        ),
        "queue": HealthComponent(
            "queue",
            _bounded_score(queue_score),
            _state(_bounded_score(queue_score)),
            tuple(sorted(set(queue_reasons))),
        ),
        "validation": HealthComponent(
            "validation",
            _bounded_score(validation_score),
            _state(_bounded_score(validation_score)),
            tuple(sorted(set(validation_reasons))),
        ),
        "recovery": HealthComponent(
            "recovery",
            _bounded_score(recovery_score),
            _state(_bounded_score(recovery_score)),
            tuple(sorted(set(recovery_reasons))),
        ),
        "storage": HealthComponent(
            "storage",
            _bounded_score(storage_score),
            _state(_bounded_score(storage_score)),
            tuple(sorted(set(storage_reasons))),
        ),
        "reporting": HealthComponent(
            "reporting",
            _bounded_score(reporting_score),
            _state(_bounded_score(reporting_score)),
            tuple(sorted(set(reporting_reasons))),
        ),
    }

    weights = {
        "governance": 0.20,
        "queue": 0.20,
        "validation": 0.15,
        "recovery": 0.20,
        "storage": 0.15,
        "reporting": 0.10,
    }
    weighted = sum(
        components[name].score * weight
        for name, weight in weights.items()
    )
    overall_score = _bounded_score(round(weighted))

    # Hard fail-closed caps.
    hard_blockers: list[str] = []
    if queue.get("audit_valid") is False:
        overall_score = min(overall_score, 49)
        hard_blockers.append("queue_transition_audit_invalid")
    if decision == "BLOCK":
        overall_score = min(overall_score, 49)
        hard_blockers.append("recovery_blocked")
    if critical_alerts:
        overall_score = min(overall_score, 69)
        hard_blockers.append("critical_operational_alerts")

    overall_state = _state(overall_score)

    return {
        "score": overall_score,
        "state": overall_state,
        "components": {
            name: component.to_dict()
            for name, component in components.items()
        },
        "weights": weights,
        "hard_blockers": sorted(set(hard_blockers)),
        "scoring": {
            "range": [0, 100],
            "healthy_min": 90,
            "degraded_min": 70,
            "blocked_max": 69,
            "weighted": True,
            "fail_closed_caps": True,
        },
        "read_only": True,
        "aggregate_only": True,
        "automatic_mutation": False,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
