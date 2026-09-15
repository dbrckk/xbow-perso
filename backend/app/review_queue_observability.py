from __future__ import annotations

from typing import Any, Iterable

from .review_queue import (
    REVIEW_QUEUE_HISTORY_RETENTION,
    diff_review_queue_snapshots,
)


def summarize_review_queue_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    chronological = list(reversed(rows))
    transitions = [
        diff_review_queue_snapshots(
            dict(chronological[index - 1].get("document") or {}),
            dict(chronological[index].get("document") or {}),
        )
        for index in range(1, len(chronological))
    ]
    changed = sum(bool(item.get("changed")) for item in transitions)
    added = sum(int(item.get("added_count") or 0) for item in transitions)
    removed = sum(int(item.get("removed_count") or 0) for item in transitions)
    transition_count = len(transitions)
    return {
        "retained_snapshots": len(rows),
        "transitions": transition_count,
        "changed_transitions": changed,
        "added_tasks": added,
        "removed_tasks": removed,
        "change_rate": (
            round(changed / transition_count, 4)
            if transition_count
            else 0.0
        ),
        "read_only": True,
        "aggregate_only": True,
        "contains_task_ids": False,
    }


def aggregate_review_queue_churn(
    storage_backend: Any,
    campaign_ids: Iterable[str],
    *,
    retention_limit: int = REVIEW_QUEUE_HISTORY_RETENTION,
) -> dict[str, Any]:
    history_fn = getattr(storage_backend, "list_review_queue_snapshots", None)
    supported = callable(history_fn)
    campaign_ids = [str(item) for item in campaign_ids if str(item)]
    result = {
        "supported": supported,
        "campaigns_checked": len(campaign_ids) if supported else 0,
        "campaigns_with_history": 0,
        "retained_snapshots": 0,
        "transitions": 0,
        "changed_transitions": 0,
        "added_tasks": 0,
        "removed_tasks": 0,
        "change_rate": 0.0,
        "retention_limit": retention_limit,
        "campaigns_at_capacity": 0,
        "read_only": True,
        "aggregate_only": True,
        "contains_task_ids": False,
    }
    if not supported:
        return result

    for campaign_id in campaign_ids:
        rows = history_fn(campaign_id, limit=retention_limit)
        summary = summarize_review_queue_rows(rows)
        if rows:
            result["campaigns_with_history"] += 1
        if len(rows) >= retention_limit:
            result["campaigns_at_capacity"] += 1
        for key in (
            "retained_snapshots",
            "transitions",
            "changed_transitions",
            "added_tasks",
            "removed_tasks",
        ):
            result[key] += int(summary[key])

    transitions = int(result["transitions"])
    result["change_rate"] = (
        round(int(result["changed_transitions"]) / transitions, 4)
        if transitions
        else 0.0
    )
    return result
