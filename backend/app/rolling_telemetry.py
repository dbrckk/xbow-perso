from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any


ALLOWED_WINDOWS = (300, 3600)
MAX_EVENTS = 10000


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def build_rolling_telemetry(
    events: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build bounded rolling aggregates from redacted worker outcome events."""
    current = now or datetime.now(timezone.utc)
    bounded = events[-MAX_EVENTS:]
    result: dict[str, Any] = {}

    for seconds in ALLOWED_WINDOWS:
        cutoff = current - timedelta(seconds=seconds)
        selected = []
        for event in bounded:
            at = _timestamp(event.get("at"))
            if at is None or at < cutoff or at > current:
                continue
            if event.get("type") != "worker_outcome":
                continue
            selected.append(event)

        statuses = Counter(str(item.get("status") or "unknown") for item in selected)
        durations = [
            int(item["duration_ms"])
            for item in selected
            if isinstance(item.get("duration_ms"), int)
            and 0 <= int(item["duration_ms"]) <= 86_400_000
        ]
        completed = sum(statuses.values())
        failed = int(statuses.get("failed") or 0)
        result[str(seconds)] = {
            "events": completed,
            "failed": failed,
            "failure_rate": (failed / completed if completed else 0.0),
            "throughput_per_minute": completed / (seconds / 60),
            "duration_ms": {
                "p50": _percentile(durations, 0.50),
                "p95": _percentile(durations, 0.95),
                "p99": _percentile(durations, 0.99),
            },
        }

    return {
        "windows": result,
        "source_events_considered": len(bounded),
        "source_events_cap": MAX_EVENTS,
        "read_only": True,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
