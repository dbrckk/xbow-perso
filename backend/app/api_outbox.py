from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _matches_identity(event: Mapping[str, Any], identity: Mapping[str, Any]) -> bool:
    return all(event.get(key) == value for key, value in identity.items())


def has_event(
    events: Iterable[Mapping[str, Any]],
    event_type: str,
    *,
    identity: Mapping[str, Any],
) -> bool:
    return any(
        event.get("type") == event_type and _matches_identity(event, identity)
        for event in events
    )


def append_event_once(
    events: list[dict[str, Any]],
    event: dict[str, Any],
    *,
    identity: Mapping[str, Any],
) -> bool:
    event_type = str(event.get("type") or "")
    if not event_type:
        raise ValueError("outbox event type is required")
    if not identity:
        raise ValueError("outbox event identity is required")
    if has_event(events, event_type, identity=identity):
        return False
    events.append(event)
    return True


def pending_request_id(
    events: Iterable[Mapping[str, Any]],
    *,
    requested_type: str,
    completed_type: str,
    identity: Mapping[str, Any] | None = None,
) -> str | None:
    identity = identity or {}
    completed = {
        str(event.get("request_id"))
        for event in events
        if event.get("type") == completed_type
        and event.get("request_id")
        and _matches_identity(event, identity)
    }
    materialized = list(events)
    for event in reversed(materialized):
        request_id = event.get("request_id")
        if (
            event.get("type") == requested_type
            and isinstance(request_id, str)
            and request_id
            and request_id not in completed
            and _matches_identity(event, identity)
        ):
            return request_id
    return None
