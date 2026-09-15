from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


DOMAINS = ("workload", "control_plane", "observability")
MAX_HISTORY = 1000


def _now(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def apply_domain_incidents(
    history: list[dict[str, Any]],
    snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Apply independent lifecycle transitions for each operational domain."""
    items = [dict(item) for item in history[-MAX_HISTORY:]]
    incoming = snapshot.get("incidents") or {}
    timestamp = _now(now)

    for domain in DOMAINS:
        incident = incoming.get(domain)
        active = next(
            (
                item
                for item in reversed(items)
                if item.get("domain") == domain and item.get("status") != "resolved"
            ),
            None,
        )

        if incident is None:
            if active is not None:
                active["status"] = "resolved"
                active["resolved_at"] = timestamp
            continue

        fingerprint = str(incident["fingerprint"])
        if active and active.get("fingerprint") == fingerprint:
            active["severity"] = str(incident["severity"])
            active["last_seen_at"] = timestamp
            continue

        if active is not None:
            active["status"] = "resolved"
            active["resolved_at"] = timestamp

        items.append({
            "domain": domain,
            "fingerprint": fingerprint,
            "dedupe_key": str(incident["dedupe_key"]),
            "severity": str(incident["severity"]),
            "status": "opened",
            "opened_at": timestamp,
            "last_seen_at": timestamp,
            "acknowledged_at": None,
            "resolved_at": None,
        })

    return items[-MAX_HISTORY:]


def active_incidents_by_domain(history: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    result: dict[str, dict[str, Any] | None] = {}
    for domain in DOMAINS:
        result[domain] = next(
            (
                item
                for item in reversed(history[-MAX_HISTORY:])
                if item.get("domain") == domain and item.get("status") != "resolved"
            ),
            None,
        )
    return result
