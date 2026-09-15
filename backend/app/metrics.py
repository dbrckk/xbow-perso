from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from .api_outbox import outbox_snapshot
from .review_queue_observability import aggregate_review_queue_churn
from .submission_audit import audit_storage_submissions

router = APIRouter()


def _age_seconds(value: Any, *, now: datetime | None = None) -> int | None:
    if not value:
        return None
    try:
        created = datetime.fromisoformat(str(value))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        return max(
            0,
            int((current - created.astimezone(timezone.utc)).total_seconds()),
        )
    except (TypeError, ValueError, OverflowError):
        return None


def build_operational_metrics(queue_backend, storage_backend) -> dict[str, Any]:
    queue_stats = queue_backend.stats()
    campaigns = storage_backend.list_campaigns()
    states = Counter(str(item.get("state") or "unknown") for item in campaigns)

    by_status = dict(queue_stats.get("by_status") or {})
    oldest_queued_age_seconds = _age_seconds(queue_stats.get("oldest_queued_at"))
    oldest_running_lease_age_seconds = _age_seconds(
        queue_stats.get("oldest_running_claimed_at")
    )

    pending_outbox_total = 0
    pending_outbox_by_kind: Counter[str] = Counter()
    oldest_outbox_age_seconds = None
    queue_audit_campaigns = 0
    queue_audit_events = 0
    queue_audit_invalid_campaigns = 0
    queue_audit_invalid_jobs = 0
    queue_audit_fn = getattr(queue_backend, "campaign_transition_audit", None)
    queue_audit_supported = callable(queue_audit_fn)
    for campaign in campaigns:
        campaign_id = str(campaign.get("id") or "")
        if campaign_id and queue_audit_supported:
            audit = queue_audit_fn(campaign_id)
            queue_audit_campaigns += 1
            queue_audit_events += int(audit.get("events") or 0)
            invalid_jobs = list(audit.get("invalid_jobs") or [])
            queue_audit_invalid_jobs += len(invalid_jobs)
            if not bool(audit.get("valid")):
                queue_audit_invalid_campaigns += 1

        events = campaign.get("events") or []
        if not isinstance(events, list):
            continue
        snapshot = outbox_snapshot(events, max_items=1)
        pending_outbox_total += int(snapshot["pending_total"])
        pending_outbox_by_kind.update(snapshot["pending_by_kind"])
        age = _age_seconds(snapshot.get("oldest_pending_at"))
        if age is not None:
            oldest_outbox_age_seconds = (
                age
                if oldest_outbox_age_seconds is None
                else max(oldest_outbox_age_seconds, age)
            )

    health_history_fn = getattr(
        storage_backend,
        "list_control_plane_health_snapshots",
        None,
    )
    health_snapshots = (
        health_history_fn(limit=100)
        if callable(health_history_fn)
        else []
    )
    health_latest_score = (
        int(health_snapshots[0].get("score") or 0)
        if health_snapshots
        else None
    )
    health_previous_score = (
        int(health_snapshots[1].get("score") or 0)
        if len(health_snapshots) > 1
        else None
    )
    health_delta = (
        health_latest_score - health_previous_score
        if health_latest_score is not None and health_previous_score is not None
        else None
    )
    health_trend = (
        "unknown"
        if health_delta is None
        else (
            "improving"
            if health_delta > 0
            else "degrading"
            if health_delta < 0
            else "stable"
        )
    )
    health_transitions = 0
    health_to_blocked = 0
    health_healthy_to_degraded = 0
    chronological_health = list(reversed(health_snapshots))
    previous_health_state = None
    for item in chronological_health:
        state = str(item.get("state") or "unknown")
        if previous_health_state is not None and state != previous_health_state:
            health_transitions += 1
            if state == "BLOCKED":
                health_to_blocked += 1
            if previous_health_state == "HEALTHY" and state == "DEGRADED":
                health_healthy_to_degraded += 1
        previous_health_state = state
    recent_health = chronological_health[-3:]
    persistent_health_degradation = (
        len(recent_health) == 3
        and str(recent_health[-1].get("state")) != "HEALTHY"
        and int(recent_health[-1].get("score") or 0)
        < int(recent_health[0].get("score") or 0)
        and all(
            int(recent_health[index].get("score") or 0)
            <= int(recent_health[index - 1].get("score") or 0)
            for index in range(1, len(recent_health))
        )
    )

    readiness_history_fn = getattr(
        storage_backend,
        "list_recovery_readiness_snapshots",
        None,
    )
    readiness_snapshots = (
        readiness_history_fn(limit=100)
        if callable(readiness_history_fn)
        else []
    )
    readiness_counts: Counter[str] = Counter(
        str(item.get("decision") or "unknown") for item in readiness_snapshots
    )
    readiness_transitions = 0
    ready_to_block_regressions = 0
    chronological = list(reversed(readiness_snapshots))
    previous_decision = None
    for item in chronological:
        decision = str(item.get("decision") or "unknown")
        if previous_decision is not None and decision != previous_decision:
            readiness_transitions += 1
            if previous_decision == "READY" and decision == "BLOCK":
                ready_to_block_regressions += 1
        previous_decision = decision

    review_queue_churn = aggregate_review_queue_churn(
        storage_backend,
        [str(item.get("id") or "") for item in campaigns],
    )
    submission_integrity = audit_storage_submissions(storage_backend)

    metrics = {
        "campaigns_total": len(campaigns),
        "campaigns_by_state": dict(sorted(states.items())),
        "jobs_total": int(queue_stats.get("total") or 0),
        "jobs_by_status": {
            key: int(value) for key, value in sorted(by_status.items())
        },
        "queue_storage": str(queue_stats.get("storage") or "unknown"),
        "oldest_queued_age_seconds": oldest_queued_age_seconds,
        "oldest_running_lease_age_seconds": oldest_running_lease_age_seconds,
        "pending_outbox_total": pending_outbox_total,
        "pending_outbox_by_kind": dict(sorted(pending_outbox_by_kind.items())),
        "oldest_outbox_pending_age_seconds": oldest_outbox_age_seconds,
        "review_queue_churn": review_queue_churn,
        "control_plane_health": {
            "supported": callable(health_history_fn),
            "latest_score": health_latest_score,
            "previous_score": health_previous_score,
            "delta": health_delta,
            "trend": health_trend,
            "latest_state": (
                str(health_snapshots[0].get("state"))
                if health_snapshots
                else None
            ),
            "snapshots": len(health_snapshots),
            "transitions": health_transitions,
            "to_blocked_transitions": health_to_blocked,
            "healthy_to_degraded_transitions": health_healthy_to_degraded,
            "persistent_degradation": persistent_health_degradation,
        },
        "recovery_readiness": {
            "supported": callable(readiness_history_fn),
            "latest_decision": (
                str(readiness_snapshots[0].get("decision"))
                if readiness_snapshots
                else None
            ),
            "snapshots": len(readiness_snapshots),
            "by_decision": dict(sorted(readiness_counts.items())),
            "transitions": readiness_transitions,
            "ready_to_block_regressions": ready_to_block_regressions,
        },
        "submission_integrity": submission_integrity,
        "queue_transition_audit": {
            "supported": queue_audit_supported,
            "campaigns_checked": queue_audit_campaigns,
            "events_checked": queue_audit_events,
            "invalid_campaigns": queue_audit_invalid_campaigns,
            "invalid_jobs": queue_audit_invalid_jobs,
            "valid": (
                queue_audit_invalid_campaigns == 0
                if queue_audit_supported
                else None
            ),
        },
        "read_only": True,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
        "contains_outbox_identities": False,
    }
    return metrics


@router.get("/api/metrics")
def operational_metrics():
    from .main import queue, storage

    return build_operational_metrics(queue(), storage())
