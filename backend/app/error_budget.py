from __future__ import annotations

import os
from typing import Any


def _target_success_rate() -> float:
    raw = os.getenv("XBOW_SLO_TARGET_SUCCESS_RATE", "0.99")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("XBOW_SLO_TARGET_SUCCESS_RATE must be numeric") from exc
    if not 0.90 <= value < 1.0:
        raise ValueError("XBOW_SLO_TARGET_SUCCESS_RATE must be >= 0.90 and < 1.0")
    return value


def _burn(failure_rate: float, budget: float) -> float:
    return failure_rate / budget if budget > 0 else float("inf")


def build_error_budget_status(telemetry: dict[str, Any]) -> dict[str, Any]:
    """Evaluate multi-window error-budget consumption from rolling telemetry."""
    target = _target_success_rate()
    budget = 1.0 - target
    windows = telemetry.get("windows") or {}

    short = windows.get("300") or {}
    long = windows.get("3600") or {}
    short_events = int(short.get("events") or 0)
    long_events = int(long.get("events") or 0)
    short_burn = _burn(float(short.get("failure_rate") or 0.0), budget)
    long_burn = _burn(float(long.get("failure_rate") or 0.0), budget)

    alerts: list[dict[str, Any]] = []

    # Require minimum sample counts to avoid one isolated failure creating a
    # high-severity incident signal on an otherwise idle installation.
    if short_events >= 20 and long_events >= 100:
        if short_burn >= 14.4 and long_burn >= 6.0:
            alerts.append({"code": "fast_error_budget_burn", "severity": "critical"})
        elif short_burn >= 6.0 and long_burn >= 3.0:
            alerts.append({"code": "elevated_error_budget_burn", "severity": "warning"})

    state = (
        "critical"
        if any(item["severity"] == "critical" for item in alerts)
        else "degraded"
        if alerts
        else "healthy"
    )
    return {
        "state": state,
        "target_success_rate": target,
        "error_budget": budget,
        "burn_rate": {"300": short_burn, "3600": long_burn},
        "sample_count": {"300": short_events, "3600": long_events},
        "alerts": alerts,
        "read_only": True,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
