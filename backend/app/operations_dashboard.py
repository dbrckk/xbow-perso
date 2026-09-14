from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter

from .metrics import build_operational_metrics
from .operational_alerts import build_operational_alerts
from .recovery_readiness import recovery_readiness_history

router = APIRouter()


def build_operations_dashboard(queue_backend, storage_backend) -> dict[str, Any]:
    metrics = build_operational_metrics(queue_backend, storage_backend)
    alerts = build_operational_alerts(metrics)
    history = recovery_readiness_history(storage_backend, limit=25)

    campaigns = storage_backend.list_campaigns()
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
    if critical_alerts:
        blocked_reasons.append("critical_operational_alert")

    if recovery.get("latest_decision") == "REVIEW":
        degraded_reasons.append("recovery_operator_review_required")
    if failed_jobs:
        degraded_reasons.append("failed_jobs")
    if warning_alerts:
        degraded_reasons.append("operational_warning")
    if int(metrics.get("pending_outbox_total") or 0):
        degraded_reasons.append("pending_outbox")

    if blocked_reasons:
        health = "BLOCKED"
    elif degraded_reasons:
        health = "DEGRADED"
    else:
        health = "HEALTHY"

    return {
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
        },
        "read_only": True,
        "aggregate_only": True,
        "automatic_worker_start": False,
        "automatic_mutation": False,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }


@router.get("/api/dashboard/operations")
def operations_dashboard():
    from .main import queue, storage

    return build_operations_dashboard(queue(), storage())
