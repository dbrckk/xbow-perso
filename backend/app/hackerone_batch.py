from __future__ import annotations

from copy import deepcopy
from typing import Any

from .storage import CampaignConflictError


_TERMINAL_MEMBER_STATES = {"done", "review", "blocked", "cancelled"}


def _active_job_counts(queue, campaign_id: str) -> dict[str, int]:
    return queue.campaign_job_status_counts(campaign_id)


def _campaign_state(store, campaign_id: str) -> str | None:
    raw = store.get_campaign(campaign_id)
    if not raw:
        return None
    return str(raw.get("state") or "")


def _member_finished(queue, store, member: dict[str, Any]) -> tuple[bool, str | None]:
    campaign_id = str(member.get("campaign_id") or "")
    state = _campaign_state(store, campaign_id)
    if state is None:
        return True, "blocked"
    if state == "cancelled":
        return True, "cancelled"
    if state == "failed":
        return True, "blocked"
    if state == "completed":
        return True, "done"

    counts = _active_job_counts(queue, campaign_id)
    if int(counts.get("queued") or 0) > 0 or int(counts.get("running") or 0) > 0:
        return False, None

    total_terminal = sum(
        int(counts.get(key) or 0)
        for key in ("completed", "failed", "cancelled")
    )
    if total_terminal == 0:
        return False, None
    if int(counts.get("failed") or 0) > 0:
        return True, "review"
    return True, "done"


def _start_member(member: dict[str, Any]) -> tuple[str, str | None]:
    from fastapi import HTTPException

    from .main import start_campaign

    campaign_id = str(member.get("campaign_id") or "")
    try:
        start_campaign(campaign_id)
    except HTTPException as exc:
        return "blocked", str(exc.detail)
    except Exception as exc:
        return "blocked", exc.__class__.__name__
    return "running", None


def _summarize_members(members: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "ready": 0,
        "running": 0,
        "done": 0,
        "review": 0,
        "blocked": 0,
        "cancelled": 0,
    }
    for member in members:
        status = str(member.get("status") or "ready")
        if status in counts:
            counts[status] += 1
    return counts


def _batch_state(members: list[dict[str, Any]]) -> str:
    statuses = {str(member.get("status") or "ready") for member in members}
    if statuses and statuses.issubset(_TERMINAL_MEMBER_STATES):
        return "completed"
    if "running" in statuses:
        return "running"
    return "queued"


def reconcile_hackerone_batch(queue, store, batch_id: str) -> dict[str, Any] | None:
    for _ in range(3):
        record = store.get_hackerone_batch_record(batch_id)
        if not record:
            return None
        current, version = record
        if str(current.get("state")) in {"completed", "cancelled"}:
            return current

        batch = deepcopy(current)
        members = list(batch.get("members") or [])
        changed = False

        for member in members:
            status = str(member.get("status") or "ready")
            if status != "running":
                continue
            finished, final_status = _member_finished(queue, store, member)
            if finished and final_status:
                member["status"] = final_status
                changed = True

        mode = str(batch.get("mode") or "sequential")
        if mode == "sequential":
            has_running = any(
                str(member.get("status") or "") == "running"
                for member in members
            )
            if not has_running:
                next_member = next(
                    (
                        member
                        for member in members
                        if str(member.get("status") or "ready") == "ready"
                    ),
                    None,
                )
                if next_member is not None:
                    next_status, reason = _start_member(next_member)
                    next_member["status"] = next_status
                    if reason:
                        next_member["reason"] = reason[:500]
                    changed = True

        batch["members"] = members
        batch["summary"] = _summarize_members(members)
        next_state = _batch_state(members)
        if next_state != batch.get("state"):
            batch["state"] = next_state
            changed = True

        if not changed:
            return current

        from .main import utcnow

        batch["updated_at"] = utcnow()
        try:
            store.save_hackerone_batch(batch, expected_version=version)
            return batch
        except CampaignConflictError:
            continue
    return store.get_hackerone_batch(batch_id)


def reconcile_hackerone_batches(queue, store, *, limit: int = 20) -> int:
    batches = store.list_hackerone_batches(limit=limit)
    reconciled = 0
    for batch in reversed(batches):
        if str(batch.get("state")) in {"completed", "cancelled"}:
            continue
        try:
            reconcile_hackerone_batch(queue, store, str(batch["id"]))
        except (CampaignConflictError, ValueError, KeyError):
            continue
        reconciled += 1
    return reconciled
