from __future__ import annotations

import hashlib
import json
from typing import Any

_ALLOWED_TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({"queued"}),
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"queued", "completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


def transition_allowed(from_status: str | None, to_status: str) -> bool:
    return to_status in _ALLOWED_TRANSITIONS.get(from_status, frozenset())


def build_transition_event(
    *,
    job_id: str,
    campaign_id: str,
    kind: str,
    seq: int,
    from_status: str | None,
    to_status: str,
    actor: str,
    reason: str,
    at: str,
    previous_hash: str | None,
) -> dict[str, Any]:
    if seq < 1:
        raise ValueError("transition sequence must be positive")
    if not transition_allowed(from_status, to_status):
        raise ValueError(f"invalid job transition: {from_status!r} -> {to_status!r}")

    payload = {
        "job_id": str(job_id),
        "campaign_id": str(campaign_id),
        "kind": str(kind),
        "seq": int(seq),
        "from_status": from_status,
        "to_status": str(to_status),
        "actor": str(actor),
        "reason": str(reason),
        "at": str(at),
        "previous_hash": previous_hash,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return {**payload, "event_hash": hashlib.sha256(canonical).hexdigest()}


def verify_transition_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    previous_hash: str | None = None
    previous_status: str | None = None

    for expected_seq, event in enumerate(events, start=1):
        try:
            seq = int(event.get("seq", 0))
        except (TypeError, ValueError):
            return {
                "valid": False,
                "reason": "invalid transition sequence",
                "checked": expected_seq - 1,
            }
        if seq != expected_seq:
            return {
                "valid": False,
                "reason": "transition sequence gap",
                "checked": expected_seq - 1,
            }

        from_status = event.get("from_status")
        to_status = str(event.get("to_status") or "")
        if from_status != previous_status:
            return {
                "valid": False,
                "reason": "transition status discontinuity",
                "checked": expected_seq - 1,
            }
        if not transition_allowed(from_status, to_status):
            return {
                "valid": False,
                "reason": "invalid status transition",
                "checked": expected_seq - 1,
            }
        if event.get("previous_hash") != previous_hash:
            return {
                "valid": False,
                "reason": "transition hash discontinuity",
                "checked": expected_seq - 1,
            }

        rebuilt = build_transition_event(
            job_id=str(event.get("job_id") or ""),
            campaign_id=str(event.get("campaign_id") or ""),
            kind=str(event.get("kind") or ""),
            seq=seq,
            from_status=from_status,
            to_status=to_status,
            actor=str(event.get("actor") or ""),
            reason=str(event.get("reason") or ""),
            at=str(event.get("at") or ""),
            previous_hash=previous_hash,
        )
        if rebuilt["event_hash"] != event.get("event_hash"):
            return {
                "valid": False,
                "reason": "transition hash mismatch",
                "checked": expected_seq - 1,
            }

        previous_hash = rebuilt["event_hash"]
        previous_status = to_status

    return {
        "valid": True,
        "reason": None,
        "checked": len(events),
        "final_status": previous_status,
        "head_hash": previous_hash,
    }
