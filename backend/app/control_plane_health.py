from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .metrics import build_operational_metrics
from .operational_alerts import build_operational_alerts

router = APIRouter()

_WEIGHTS = {
    "governance": 20,
    "queue_integrity": 30,
    "worker_runtime": 20,
    "queue_flow": 15,
    "delivery": 15,
}


def _domain(score: int, reasons: list[str]) -> dict[str, Any]:
    bounded = max(0, min(100, int(score)))
    return {
        "score": bounded,
        "status": "HEALTHY" if bounded >= 85 else "DEGRADED",
        "reasons": reasons,
    }


def build_control_plane_health(
    metrics: dict[str, Any],
    alerts: dict[str, Any],
) -> dict[str, Any]:
    """Build an aggregate, advisory health model from existing read-only signals."""
    hard_blockers: list[str] = []

    governance_score = 100
    governance_reasons: list[str] = []
    invalid_audit = int(metrics.get("invalid_campaign_audit_chains") or 0)
    legacy_audit = int(metrics.get("campaigns_with_legacy_audit_events") or 0)
    if invalid_audit:
        governance_score = 0
        governance_reasons.append("campaign_audit_invalid")
        hard_blockers.append("campaign_audit_invalid")
    elif legacy_audit:
        governance_score = 80
        governance_reasons.append("legacy_audit_events_present")

    queue_score = 100
    queue_reasons: list[str] = []
    queue_available = metrics.get("queue_recovery_available")
    queue_critical = int(metrics.get("queue_recovery_critical_issues") or 0)
    queue_warning = int(metrics.get("queue_recovery_warning_issues") or 0)
    queue_truncated = bool(metrics.get("queue_recovery_assessment_truncated"))
    if queue_critical or queue_truncated:
        queue_score = 0
        queue_reasons.append("queue_consistency_invalid")
        hard_blockers.append("queue_consistency_invalid")
    elif queue_available is False:
        queue_score = 50
        queue_reasons.append("queue_recovery_unavailable")
    elif queue_warning:
        queue_score = 70
        queue_reasons.append("queue_recovery_review")
    elif metrics.get("queue_recovery_safe_to_resume") is False:
        queue_score = 70
        queue_reasons.append("queue_recovery_review")

    watchdog = metrics.get("worker_watchdog") or {}
    watchdog_status = str(watchdog.get("status") or "unknown").lower()
    worker_reasons = [
        str(item.get("code") or "worker_watchdog_issue")
        for item in list(watchdog.get("issues") or [])[:20]
        if isinstance(item, dict)
    ]
    if watchdog_status == "ok":
        worker_score = 100
    elif watchdog_status == "warning":
        worker_score = 65
    elif watchdog_status == "error":
        worker_score = 25
    else:
        worker_score = 50
        worker_reasons.append("worker_watchdog_unknown")

    alert_items = [
        item
        for item in list(alerts.get("alerts") or [])
        if isinstance(item, dict)
    ]
    alert_codes = {
        str(item.get("code") or "")
        for item in alert_items
        if str(item.get("code") or "")
    }

    queue_flow_reasons: list[str] = []
    if "running_lease_stale" in alert_codes or "queue_stalled" in alert_codes:
        queue_flow_score = 20
        queue_flow_reasons.extend(
            sorted(
                alert_codes
                & {"running_lease_stale", "queue_stalled"}
            )
        )
    elif alert_codes & {"queue_backlog", "running_jobs_high", "failed_jobs"}:
        queue_flow_score = 60
        queue_flow_reasons.extend(
            sorted(
                alert_codes
                & {"queue_backlog", "running_jobs_high", "failed_jobs"}
            )
        )
    else:
        queue_flow_score = 100

    delivery_reasons: list[str] = []
    if "outbox_stalled" in alert_codes:
        delivery_score = 20
        delivery_reasons.append("outbox_stalled")
    elif "outbox_backlog" in alert_codes:
        delivery_score = 60
        delivery_reasons.append("outbox_backlog")
    else:
        delivery_score = 100

    if "alert_configuration_invalid" in alert_codes:
        hard_blockers.append("alert_configuration_invalid")

    domains = {
        "governance": _domain(governance_score, governance_reasons),
        "queue_integrity": _domain(queue_score, queue_reasons),
        "worker_runtime": _domain(worker_score, worker_reasons),
        "queue_flow": _domain(queue_flow_score, queue_flow_reasons),
        "delivery": _domain(delivery_score, delivery_reasons),
    }
    weighted_score = round(
        sum(domains[name]["score"] * weight for name, weight in _WEIGHTS.items())
        / 100,
        2,
    )
    blockers = sorted(set(hard_blockers))
    if blockers:
        weighted_score = min(weighted_score, 39.0)
        status = "BLOCKED"
    elif weighted_score >= 85:
        status = "HEALTHY"
    else:
        status = "DEGRADED"

    critical_alerts = sum(
        str(item.get("severity") or "").lower() == "critical"
        for item in alert_items
    )
    warning_alerts = sum(
        str(item.get("severity") or "").lower() == "warning"
        for item in alert_items
    )

    return {
        "status": status,
        "score": weighted_score,
        "domains": domains,
        "weights": dict(_WEIGHTS),
        "hard_blockers": blockers,
        "alert_counts": {
            "critical": critical_alerts,
            "warning": warning_alerts,
        },
        "read_only": True,
        "aggregate_only": True,
        "advisory_only": True,
        "automatic_repair": False,
        "automatic_execution_change": False,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
        "contains_worker_identities": False,
    }


@router.get("/api/operations/health")
def control_plane_health():
    from .main import queue, storage

    metrics = build_operational_metrics(queue(), storage())
    try:
        alerts = build_operational_alerts(metrics)
    except ValueError:
        alerts = {
            "status": "alert",
            "alerts": [
                {
                    "code": "alert_configuration_invalid",
                    "severity": "critical",
                    "value": 1,
                    "threshold": 1,
                }
            ],
            "read_only": True,
            "aggregate_only": True,
        }
    return build_control_plane_health(metrics, alerts)
