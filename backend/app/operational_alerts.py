from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

from .alert_delivery import deliver_alerts
from .metrics import build_operational_metrics

router = APIRouter()


def _threshold(name: str, default: int, low: int, high: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def build_operational_alerts(metrics: dict[str, Any]) -> dict[str, Any]:
    failed_limit = _threshold("XBOW_ALERT_FAILED_JOBS", 1, 1, 100000)
    queued_limit = _threshold("XBOW_ALERT_QUEUED_JOBS", 20, 1, 100000)
    running_limit = _threshold("XBOW_ALERT_RUNNING_JOBS", 20, 1, 100000)
    queue_age_limit = _threshold("XBOW_ALERT_QUEUE_AGE_SECONDS", 300, 30, 86400)
    running_lease_age_limit = _threshold(
        "XBOW_ALERT_RUNNING_LEASE_AGE_SECONDS",
        900,
        30,
        86400,
    )
    outbox_limit = _threshold("XBOW_ALERT_PENDING_OUTBOX", 20, 1, 100000)
    outbox_age_limit = _threshold("XBOW_ALERT_OUTBOX_AGE_SECONDS", 300, 30, 86400)

    statuses = metrics.get("jobs_by_status") or {}
    failed = int(statuses.get("failed") or 0)
    queued = int(statuses.get("queued") or 0)
    running = int(statuses.get("running") or 0)
    queue_age = metrics.get("oldest_queued_age_seconds")
    running_lease_age = metrics.get("oldest_running_lease_age_seconds")
    pending_outbox = int(metrics.get("pending_outbox_total") or 0)
    outbox_age = metrics.get("oldest_outbox_pending_age_seconds")
    recovery = metrics.get("recovery_readiness") or {}
    health = metrics.get("control_plane_health") or {}
    slo = metrics.get("slo")
    if slo is None:
        from .slo import build_platform_slos

        slo = build_platform_slos(metrics)
    latest_recovery_decision = recovery.get("latest_decision")
    ready_to_block_regressions = int(
        recovery.get("ready_to_block_regressions") or 0
    )

    alerts: list[dict[str, Any]] = []
    if failed >= failed_limit:
        alerts.append(
            {
                "code": "failed_jobs",
                "severity": "critical",
                "value": failed,
                "threshold": failed_limit,
            }
        )
    if queued >= queued_limit:
        alerts.append(
            {
                "code": "queue_backlog",
                "severity": "warning",
                "value": queued,
                "threshold": queued_limit,
            }
        )
    if queue_age is not None and int(queue_age) >= queue_age_limit:
        alerts.append(
            {
                "code": "queue_stalled",
                "severity": "critical",
                "value": int(queue_age),
                "threshold": queue_age_limit,
            }
        )
    if running >= running_limit:
        alerts.append(
            {
                "code": "running_jobs_high",
                "severity": "warning",
                "value": running,
                "threshold": running_limit,
            }
        )

    if (
        running_lease_age is not None
        and int(running_lease_age) >= running_lease_age_limit
    ):
        alerts.append(
            {
                "code": "running_lease_stale",
                "severity": "critical",
                "value": int(running_lease_age),
                "threshold": running_lease_age_limit,
            }
        )

    if pending_outbox >= outbox_limit:
        alerts.append(
            {
                "code": "outbox_backlog",
                "severity": "warning",
                "value": pending_outbox,
                "threshold": outbox_limit,
            }
        )
    if outbox_age is not None and int(outbox_age) >= outbox_age_limit:
        alerts.append(
            {
                "code": "outbox_stalled",
                "severity": "critical",
                "value": int(outbox_age),
                "threshold": outbox_age_limit,
            }
        )

    if latest_recovery_decision == "BLOCK":
        alerts.append(
            {
                "code": "recovery_readiness_block",
                "severity": "critical",
                "value": "BLOCK",
                "threshold": None,
            }
        )
    if ready_to_block_regressions > 0:
        alerts.append(
            {
                "code": "recovery_ready_to_block_regression",
                "severity": "critical",
                "value": ready_to_block_regressions,
                "threshold": 1,
            }
        )

    if bool(health.get("persistent_degradation")):
        alerts.append(
            {
                "code": "control_plane_persistent_degradation",
                "severity": "critical",
                "value": str(health.get("latest_state") or "unknown"),
                "threshold": 3,
            }
        )
    if str(health.get("trend") or "") == "degrading":
        alerts.append(
            {
                "code": "control_plane_health_degrading",
                "severity": "warning",
                "value": int(health.get("delta") or 0),
                "threshold": 0,
            }
        )

    if str(slo.get("state") or "") == "EXHAUSTED":
        alerts.append(
            {
                "code": "slo_error_budget_exhausted",
                "severity": "critical",
                "value": list((slo.get("summary") or {}).get("exhausted_slos") or []),
                "threshold": 0,
            }
        )
    elif str(slo.get("state") or "") == "AT_RISK":
        alerts.append(
            {
                "code": "slo_error_budget_at_risk",
                "severity": "warning",
                "value": list((slo.get("summary") or {}).get("at_risk_slos") or []),
                "threshold": 0,
            }
        )

    return {
        "status": "alert" if alerts else "ok",
        "alerts": alerts,
        "read_only": True,
        "aggregate_only": True,
    }


@router.get("/api/alerts")
def operational_alerts():
    from .main import queue, storage

    metrics = build_operational_metrics(queue(), storage())
    return build_operational_alerts(metrics)


@router.post("/api/alerts/deliver")
def deliver_operational_alerts():
    from .main import queue, storage

    metrics = build_operational_metrics(queue(), storage())
    alerts = build_operational_alerts(metrics)
    return deliver_alerts(alerts)
