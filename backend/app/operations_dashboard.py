from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter

from .control_plane_health import (
    build_control_plane_health,
    control_plane_health_history,
    record_control_plane_health,
)
from .metrics import build_operational_metrics
from .operational_alerts import build_operational_alerts
from .recovery_readiness import recovery_readiness_history
from .slo import attach_historical_slo_windows, build_platform_slos
from .submission_audit import audit_storage_submissions

router = APIRouter()


def build_operations_dashboard(queue_backend, storage_backend) -> dict[str, Any]:
    metrics = build_operational_metrics(queue_backend, storage_backend)
    slo = attach_historical_slo_windows(
        build_platform_slos(metrics),
        storage_backend,
    )
    alert_metrics = {**metrics, "slo": slo}
    alerts = build_operational_alerts(alert_metrics)
    history = recovery_readiness_history(storage_backend, limit=25)

    campaigns = storage_backend.list_campaigns()
    submission_audit = audit_storage_submissions(storage_backend)
    campaign_states = Counter(str(item.get("state") or "unknown") for item in campaigns)
    failed_jobs = int((metrics.get("jobs_by_status") or {}).get("failed") or 0)
    queue_audit = metrics.get("queue_transition_audit") or {}
    recovery = metrics.get("recovery_readiness") or {}

    critical_alerts = sum(
        str(item.get("severity") or "") == "critical"
        for item in alerts.get("alerts") or []
    )
    warning_alerts = sum(
        str(item.get("severity") or "") == "warning"
        for item in alerts.get("alerts") or []
    )

    blocked_reasons: list[str] = []
    degraded_reasons: list[str] = []

    if recovery.get("latest_decision") == "BLOCK":
        blocked_reasons.append("recovery_readiness_block")
    if not bool(queue_audit.get("valid", True)):
        blocked_reasons.append("queue_transition_audit_invalid")
    blocking_alert_codes = {
        "queue_stalled",
        "running_lease_stale",
        "recovery_readiness_block",
        "recovery_ready_to_block_regression",
        "control_plane_persistent_degradation",
    }
    if any(
        str(item.get("code") or "") in blocking_alert_codes
        for item in alerts.get("alerts") or []
    ):
        blocked_reasons.append("critical_operational_alert")

    if recovery.get("latest_decision") == "REVIEW":
        degraded_reasons.append("recovery_operator_review_required")
    if failed_jobs:
        degraded_reasons.append("failed_jobs")
    if warning_alerts:
        degraded_reasons.append("operational_warning")
    if int(metrics.get("pending_outbox_total") or 0):
        degraded_reasons.append("pending_outbox")
    if submission_audit.get("supported") and not submission_audit.get("valid"):
        degraded_reasons.append("submission_event_audit_invalid")

    if blocked_reasons:
        health = "BLOCKED"
    elif degraded_reasons:
        health = "DEGRADED"
    else:
        health = "HEALTHY"

    dashboard = {
        "health": health,
        "blocked_reasons": sorted(set(blocked_reasons)),
        "degraded_reasons": sorted(set(degraded_reasons)),
        "summary": {
            "campaigns_total": len(campaigns),
            "campaigns_by_state": dict(sorted(campaign_states.items())),
            "jobs_total": int(metrics.get("jobs_total") or 0),
            "jobs_by_status": dict(metrics.get("jobs_by_status") or {}),
            "failed_jobs": failed_jobs,
            "pending_outbox_total": int(metrics.get("pending_outbox_total") or 0),
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
        },
        "recovery": {
            "latest_decision": recovery.get("latest_decision"),
            "snapshots": int(recovery.get("snapshots") or 0),
            "transitions": int(recovery.get("transitions") or 0),
            "ready_to_block_regressions": int(
                recovery.get("ready_to_block_regressions") or 0
            ),
            "recent_transitions": history.get("transitions") or [],
        },
        "submission_integrity": submission_audit,
        "queue_integrity": {
            "storage": metrics.get("queue_storage"),
            "audit_valid": queue_audit.get("valid"),
            "audit_campaigns_checked": int(queue_audit.get("campaigns_checked") or 0),
            "audit_events_checked": int(queue_audit.get("events_checked") or 0),
            "audit_invalid_campaigns": int(queue_audit.get("invalid_campaigns") or 0),
            "audit_invalid_jobs": int(queue_audit.get("invalid_jobs") or 0),
        },
        "alerts": alerts.get("alerts") or [],
        "drilldowns": {
            "campaign_overview": "/api/campaigns/{campaign_id}/overview",
            "recovery_readiness": "/api/recovery/readiness",
            "recovery_history": "/api/recovery/readiness/history",
            "metrics": "/api/metrics",
            "alerts": "/api/alerts",
            "submission_audit": "/api/campaigns/{campaign_id}/reports/{artifact_id}/submission-audit",
        },
        "read_only": True,
        "aggregate_only": True,
        "automatic_worker_start": False,
        "automatic_mutation": False,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
    dashboard["control_plane_health"] = build_control_plane_health(dashboard)
    dashboard["slo"] = slo
    return dashboard


@router.get("/api/dashboard/operations")
def operations_dashboard():
    from .main import queue, storage

    store = storage()
    dashboard = build_operations_dashboard(queue(), store)
    dashboard["control_plane_health"] = record_control_plane_health(
        store,
        dashboard["control_plane_health"],
    )
    dashboard["control_plane_health_trend"] = control_plane_health_history(
        store,
        limit=25,
    )
    return dashboard


@router.get("/api/dashboard/operations/health-history")
def operations_health_history(limit: int = 100):
    from .main import storage

    try:
        return control_plane_health_history(storage(), limit=limit)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc
