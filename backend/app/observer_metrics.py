from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def observer_health_metrics(snapshot: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    def age(value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (current - parsed.astimezone(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None

    return {
        "consecutive_failures": int(snapshot.get("consecutive_failures") or 0),
        "last_success_age_seconds": age(snapshot.get("last_success_at")),
        "last_failure_age_seconds": age(snapshot.get("last_failure_at")),
        "last_cycle_duration_seconds": snapshot.get("last_cycle_duration_seconds"),
        "leadership_changes": int(snapshot.get("leadership_changes") or 0),
        "leadership_lost_count": int(snapshot.get("leadership_lost_count") or 0),
        "deadline_exceeded_count": int(snapshot.get("deadline_exceeded_count") or 0),
        "circuit_open": bool(
            snapshot.get("circuit_open_until")
            and age(snapshot.get("circuit_open_until")) == 0.0
        ),
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
