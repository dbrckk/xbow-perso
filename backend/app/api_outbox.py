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


def pending_request_id(
    events: Iterable[Mapping[str, Any]],
    *,
    requested_type: str,
    completed_type: str,
    identity: Mapping[str, Any] | None = None,
) -> str | None:
    identity = identity or {}
    materialized = list(events)
    completed = {
        str(event.get("request_id"))
        for event in materialized
        if event.get("type") == completed_type
        and event.get("request_id")
        and _matches_identity(event, identity)
    }
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
