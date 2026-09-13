from __future__ import annotations

import hashlib
from collections import Counter
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


def _identity_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _request_key(event: Mapping[str, Any]) -> tuple[str, str] | None:
    event_type = event.get("type")
    if event_type == "campaign_start_requested":
        request_id = event.get("request_id")
        if isinstance(request_id, str) and request_id:
            return "campaign_start", request_id
    if event_type == "validation_requested":
        request_id = event.get("request_id")
        finding_id = event.get("finding_id")
        if isinstance(request_id, str) and request_id and isinstance(finding_id, str) and finding_id:
            return "finding_validation", request_id
    if event_type == "report_requested":
        request_id = event.get("request_id")
        purpose = event.get("purpose")
        if not isinstance(request_id, str) or not request_id:
            return None
        if purpose == "campaign_completion":
            return "campaign_completion_report", request_id
        if purpose == "manual":
            return "report_manual", request_id
    if event_type == "pentagi_dispatch_requested":
        fingerprint = event.get("dispatch_fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            return "pentagi_dispatch", fingerprint
    return None


def _completion_key(event: Mapping[str, Any]) -> tuple[str, str] | None:
    event_type = event.get("type")
    if event_type == "campaign_started":
        request_id = event.get("request_id")
        if isinstance(request_id, str) and request_id:
            return "campaign_start", request_id
    if event_type == "validation_queued":
        request_id = event.get("request_id")
        if isinstance(request_id, str) and request_id:
            return "finding_validation", request_id
    if event_type == "report_queued" and event.get("purpose") == "manual":
        request_id = event.get("request_id")
        if isinstance(request_id, str) and request_id:
            return "report_manual", request_id
    if event_type == "campaign_completed" and event.get("purpose") == "campaign_completion":
        request_id = event.get("request_id")
        if isinstance(request_id, str) and request_id:
            return "campaign_completion_report", request_id
    if event_type == "pentagi_flow_queued":
        fingerprint = event.get("dispatch_fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            return "pentagi_dispatch", fingerprint
    return None


def outbox_snapshot(
    events: Iterable[Mapping[str, Any]],
    *,
    max_items: int = 100,
) -> dict[str, Any]:
    if not 1 <= max_items <= 500:
        raise ValueError("max_items must be between 1 and 500")

    materialized = list(events)
    completed = {
        key
        for event in materialized
        if (key := _completion_key(event)) is not None
    }
    pending: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for event in materialized:
        identity_key = _request_key(event)
        if identity_key is None or identity_key in seen:
            continue
        seen.add(identity_key)
        if identity_key in completed:
            continue
        kind, raw_identity = identity_key
        requested_at = event.get("at")
        pending.append(
            {
                "kind": kind,
                "requested_at": requested_at if isinstance(requested_at, str) else None,
                "identity_digest": _identity_digest(raw_identity),
            }
        )

    pending.sort(key=lambda item: (item["requested_at"] is None, item["requested_at"] or "", item["kind"]))
    counts = Counter(item["kind"] for item in pending)
    oldest = next((item["requested_at"] for item in pending if item["requested_at"]), None)
    visible = pending[:max_items]
    return {
        "pending_total": len(pending),
        "pending_by_kind": dict(sorted(counts.items())),
        "oldest_pending_at": oldest,
        "pending": visible,
        "truncated": len(visible) < len(pending),
        "identities_redacted": True,
    }
