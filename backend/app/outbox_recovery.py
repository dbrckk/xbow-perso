from __future__ import annotations

import hashlib
from typing import Any

from .api_outbox import pending_outbox_intents
from .queue_backend import QueueBackend

_TERMINAL = {"failed", "cancelled"}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def diagnose_outbox_recovery(
    campaign_id: str,
    events: list[dict[str, Any]],
    queue: QueueBackend,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for intent in pending_outbox_intents(events):
        raw_identity = str(intent["raw_identity"])
        dedupe_key = intent.get("dedupe_key")
        job_kind = intent.get("job_kind")
        item: dict[str, Any] = {
            "kind": intent["kind"],
            "requested_at": intent.get("requested_at"),
            "identity_digest": _digest(raw_identity),
            "diagnosis": "opaque",
            "job_status": None,
            "repairable_local_audit": False,
            "_intent": intent,
            "_job": None,
        }
        if not isinstance(dedupe_key, str) or not dedupe_key:
            diagnostics.append(item)
            continue
        if not isinstance(job_kind, str) or not job_kind:
            diagnostics.append(item)
            continue

        job = queue.get_by_dedupe(campaign_id, job_kind, dedupe_key)
        item["_job"] = job
        if job is None:
            item["diagnosis"] = "job_missing"
            diagnostics.append(item)
            continue

        status = str(job.get("status") or "unknown")
        item["job_status"] = status
        item["diagnosis"] = "job_terminal" if status in _TERMINAL else "audit_missing"
        item["repairable_local_audit"] = True
        diagnostics.append(item)

    return diagnostics


def public_recovery_diagnostics(
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "kind": item["kind"],
            "requested_at": item.get("requested_at"),
            "identity_digest": item["identity_digest"],
            "diagnosis": item["diagnosis"],
            "job_status": item.get("job_status"),
            "repairable_local_audit": bool(item.get("repairable_local_audit")),
        }
        for item in diagnostics
    ]


def local_completion_event(
    diagnostic: dict[str, Any],
    *,
    at: str,
) -> dict[str, Any] | None:
    if not diagnostic.get("repairable_local_audit"):
        return None
    intent = diagnostic.get("_intent") or {}
    job = diagnostic.get("_job")
    if not isinstance(job, dict):
        return None
    request = intent.get("request_event") or {}
    completion_type = intent.get("completion_type")
    if not isinstance(completion_type, str) or not completion_type:
        return None

    event: dict[str, Any] = {
        "type": completion_type,
        "job_id": job["id"],
        "at": at,
        "reconciled_locally": True,
    }
    kind = intent.get("kind")
    if kind == "campaign_start":
        event["request_id"] = request["request_id"]
        if "policy" in request:
            event["policy"] = request["policy"]
    elif kind == "finding_validation":
        event["request_id"] = request["request_id"]
        event["finding_id"] = request["finding_id"]
    elif kind in {"report_manual", "campaign_completion_report"}:
        event["request_id"] = request["request_id"]
        event["platform"] = request["platform"]
        event["purpose"] = request["purpose"]
        event["report_job_id"] = job["id"]
    else:
        return None
    return event
