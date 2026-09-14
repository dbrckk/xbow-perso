from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from .api_outbox import outbox_snapshot

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
    for campaign in campaigns:
        campaign_id = str(campaign.get("id") or "")
        if campaign_id:
            audit = queue_backend.campaign_transition_audit(campaign_id)
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

    metrics = {
        "campaigns_total": len(campaigns),
        "campaigns_by_state": dict(sorted(states.items())),
        "jobs_total": int(queue_stats.get("total") or 0),
        "jobs_by_status": {
            key: int(value)
            for key, value in sorted(by_status.items())
        },
        "queue_storage": str(queue_stats.get("storage") or "unknown"),
        "oldest_queued_age_seconds": oldest_queued_age_seconds,
        "oldest_running_lease_age_seconds": oldest_running_lease_age_seconds,
        "pending_outbox_total": pending_outbox_total,
        "pending_outbox_by_kind": dict(sorted(pending_outbox_by_kind.items())),
        "oldest_outbox_pending_age_seconds": oldest_outbox_age_seconds,
        "queue_transition_audit": {
            "campaigns_checked": queue_audit_campaigns,
            "events_checked": queue_audit_events,
            "invalid_campaigns": queue_audit_invalid_campaigns,
            "invalid_jobs": queue_audit_invalid_jobs,
            "valid": queue_audit_invalid_campaigns == 0,
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
