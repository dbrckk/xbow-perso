from __future__ import annotations

from typing import Any


def build_observer_slo(metrics: dict[str, Any]) -> dict[str, Any]:
    """Classify health of the incident-observation control plane itself."""
    failures = int(metrics.get("consecutive_failures") or 0)
    last_success_age = metrics.get("last_success_age_seconds")
    deadline_count = int(metrics.get("deadline_exceeded_count") or 0)
    leadership_lost = int(metrics.get("leadership_lost_count") or 0)
    circuit_open = bool(metrics.get("circuit_open"))

    reasons: list[str] = []
    state = "healthy"

    if circuit_open or failures >= 3:
        state = "critical"
        reasons.append("observer_failure_circuit")
    elif failures >= 1:
        state = "degraded"
        reasons.append("observer_consecutive_failures")

    if isinstance(last_success_age, (int, float)) and last_success_age > 300:
        state = "critical"
        reasons.append("observer_stale_success")
    elif isinstance(last_success_age, (int, float)) and last_success_age > 120 and state == "healthy":
        state = "degraded"
        reasons.append("observer_delayed_success")

    if deadline_count > 0 and state == "healthy":
        state = "degraded"
        reasons.append("observer_deadline_exceeded")
    if leadership_lost > 0 and state == "healthy":
        state = "degraded"
        reasons.append("observer_leadership_lost")

    return {
        "state": state,
        "reasons": sorted(set(reasons)),
        "read_only": True,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
