from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter

router = APIRouter()


def build_operational_metrics(queue_backend, storage_backend) -> dict[str, Any]:
    queue_stats = queue_backend.stats()
    campaigns = storage_backend.list_campaigns()
    states = Counter(str(item.get("state") or "unknown") for item in campaigns)

    by_status = dict(queue_stats.get("by_status") or {})
    metrics = {
        "campaigns_total": len(campaigns),
        "campaigns_by_state": dict(sorted(states.items())),
        "jobs_total": int(queue_stats.get("total") or 0),
        "jobs_by_status": {
            key: int(value)
            for key, value in sorted(by_status.items())
        },
        "queue_storage": str(queue_stats.get("storage") or "unknown"),
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
