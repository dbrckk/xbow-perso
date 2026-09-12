from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

router = APIRouter()


def build_operational_metrics(queue_backend, storage_backend) -> dict[str, Any]:
    queue_stats = queue_backend.stats()
    campaigns = storage_backend.list_campaigns()
    states = Counter(str(item.get("state") or "unknown") for item in campaigns)

    by_status = dict(queue_stats.get("by_status") or {})
    oldest_queued_at = queue_stats.get("oldest_queued_at")
    oldest_queued_age_seconds = None
    if oldest_queued_at:
        try:
            created = datetime.fromisoformat(str(oldest_queued_at))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            oldest_queued_age_seconds = max(
                0,
                int((datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds()),
            )
        except (TypeError, ValueError, OverflowError):
            oldest_queued_age_seconds = None
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
        "read_only": True,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
    return metrics


@router.get("/api/metrics")
def operational_metrics():
    from .main import queue, storage

    return build_operational_metrics(queue(), storage())
