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


def _request_descriptor(event: Mapping[str, Any]) -> tuple[str, str, str, dict[str, Any]] | None:
    event_type = event.get("type")
    if event_type == "campaign_start_requested":
        request_id = event.get("request_id")
        if isinstance(request_id, str) and request_id:
            return "campaign_start", request_id, "campaign_started", {"request_id": request_id}
    if event_type == "validation_requested":
        request_id = event.get("request_id")
        finding_id = event.get("finding_id")
        if isinstance(request_id, str) and request_id and isinstance(finding_id, str) and finding_id:
            return (
                "finding_validation",
                request_id,
                "validation_queued",
                {"request_id": request_id, "finding_id": finding_id},
            )
    if event_type == "report_requested":
        request_id = event.get("request_id")
        platform = event.get("platform")
        purpose = event.get("purpose")
        if (
            isinstance(request_id, str)
            and request_id
            and isinstance(platform, str)
            and platform
            and isinstance(purpose, str)
            and purpose
        ):
            completion_type = "campaign_completed" if purpose == "campaign_completion" else "report_queued"
            kind = "campaign_completion_report" if purpose == "campaign_completion" else "report_manual"
            return (
                kind,
                request_id,
                completion_type,
                {"request_id": request_id, "platform": platform, "purpose": purpose},
            )
    if event_type == "pentagi_dispatch_requested":
        fingerprint = event.get("dispatch_fingerprint")
        if isinstance(fingerprint, str) and fingerprint:
            return (
                "pentagi_dispatch",
                fingerprint,
                "pentagi_flow_queued",
                {"dispatch_fingerprint": fingerprint},
            )
    return None


def outbox_snapshot(
    events: Iterable[Mapping[str, Any]],
    *,
    max_items: int = 100,
) -> dict[str, Any]:
    if not 1 <= max_items <= 500:
        raise ValueError("max_items must be between 1 and 500")

    materialized = list(events)
    pending: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for event in materialized:
        descriptor = _request_descriptor(event)
        if descriptor is None:
            continue
        kind, raw_identity, completion_type, completion_identity = descriptor
        identity_key = (kind, raw_identity)
        if identity_key in seen:
            continue
        seen.add(identity_key)
        if has_event(materialized, completion_type, identity=completion_identity):
            continue
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
