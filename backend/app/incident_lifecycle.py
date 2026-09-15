from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MAX_HISTORY = 1000


def _now(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def apply_incident_snapshot(
    history: list[dict[str, Any]],
    snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Persist lifecycle transitions from a redacted incident snapshot."""
    items = [dict(item) for item in history[-MAX_HISTORY:]]
    incident = snapshot.get("incident")
    active = next((item for item in reversed(items) if item.get("status") != "resolved"), None)

    if incident is None:
        if active is not None:
            active["status"] = "resolved"
            active["resolved_at"] = _now(now)
        return items

    fingerprint = str(incident["fingerprint"])
    severity = str(incident["severity"])
    if active and active.get("fingerprint") == fingerprint:
        active["severity"] = severity
        active["last_seen_at"] = _now(now)
        return items

    if active is not None:
        active["status"] = "resolved"
        active["resolved_at"] = _now(now)

    timestamp = _now(now)
    items.append({
        "fingerprint": fingerprint,
        "dedupe_key": str(incident["dedupe_key"]),
        "severity": severity,
        "status": "opened",
        "opened_at": timestamp,
        "last_seen_at": timestamp,
        "acknowledged_at": None,
        "resolved_at": None,
    })
    return items[-MAX_HISTORY:]


def acknowledge_incident(
    history: list[dict[str, Any]],
    fingerprint: str,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    items = [dict(item) for item in history[-MAX_HISTORY:]]
    for item in reversed(items):
        if item.get("fingerprint") == fingerprint and item.get("status") == "opened":
            item["status"] = "acknowledged"
            item["acknowledged_at"] = _now(now)
            break
    return items


def incident_reliability_stats(history: list[dict[str, Any]]) -> dict[str, Any]:
    durations = []
    openings = []
    for item in history[-MAX_HISTORY:]:
        try:
            opened = datetime.fromisoformat(str(item["opened_at"]))
            openings.append(opened)
            if item.get("resolved_at"):
                resolved = datetime.fromisoformat(str(item["resolved_at"]))
                durations.append(max(0.0, (resolved - opened).total_seconds()))
        except (KeyError, TypeError, ValueError):
            continue

    mttr = sum(durations) / len(durations) if durations else None
    gaps = [
        max(0.0, (right - left).total_seconds())
        for left, right in zip(openings, openings[1:])
    ]
    mtbf = sum(gaps) / len(gaps) if gaps else None
    return {
        "incidents_considered": len(openings),
        "resolved_incidents": len(durations),
        "mttr_seconds": mttr,
        "mtbf_seconds": mtbf,
        "history_cap": MAX_HISTORY,
        "read_only": True,
    }
