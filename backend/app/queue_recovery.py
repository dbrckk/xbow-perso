from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from .jobqueue import _job_lease_seconds

router = APIRouter()

MAX_RECOVERY_JOBS = 5000
_KNOWN_STATUSES = {"queued", "running", "completed", "failed", "cancelled"}


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def analyze_queue_recovery(
    jobs: list[dict[str, Any]],
    *,
    lease_seconds: int,
    total_jobs: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assess queue consistency without mutating or exposing job payloads."""
    if not 60 <= lease_seconds <= 86400:
        raise ValueError("lease_seconds must be between 60 and 86400")

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = current - timedelta(seconds=lease_seconds)
    future_tolerance = current + timedelta(minutes=5)
    total = len(jobs) if total_jobs is None else max(0, int(total_jobs))
    truncated = total > len(jobs)

    issues: list[dict[str, Any]] = []
    status_counts = {status: 0 for status in sorted(_KNOWN_STATUSES)}
    status_counts["unknown"] = 0
    seen_ids: set[str] = set()

    for raw in jobs:
        job = raw if isinstance(raw, dict) else {}
        job_id = str(job.get("id") or "")[:200]
        status = str(job.get("status") or "unknown").strip().lower()

        if job_id in seen_ids and job_id:
            issues.append(
                {
                    "job_id": job_id,
                    "code": "duplicate_job_id",
                    "severity": "critical",
                    "recommended_action": "manual_reconciliation",
                }
            )
        elif job_id:
            seen_ids.add(job_id)

        if status in _KNOWN_STATUSES:
            status_counts[status] += 1
        else:
            status_counts["unknown"] += 1
            issues.append(
                {
                    "job_id": job_id,
                    "code": "unknown_status",
                    "severity": "critical",
                    "recommended_action": "manual_reconciliation",
                }
            )

        claimed_by = bool(str(job.get("claimed_by") or "").strip())
        claimed_at_raw = job.get("claimed_at")
        claimed_at = _parse_timestamp(claimed_at_raw)
        attempts = _parse_int(job.get("attempts"))
        max_attempts = _parse_int(job.get("max_attempts"))

        if status == "running":
            if not claimed_by:
                issues.append(
                    {
                        "job_id": job_id,
                        "code": "running_without_owner",
                        "severity": "critical",
                        "recommended_action": "manual_reconciliation",
                    }
                )
            if not claimed_at_raw:
                issues.append(
                    {
                        "job_id": job_id,
                        "code": "running_without_claim_timestamp",
                        "severity": "critical",
                        "recommended_action": "manual_reconciliation",
                    }
                )
            elif claimed_at is None:
                issues.append(
                    {
                        "job_id": job_id,
                        "code": "invalid_claim_timestamp",
                        "severity": "critical",
                        "recommended_action": "manual_reconciliation",
                    }
                )
            elif claimed_at > future_tolerance:
                issues.append(
                    {
                        "job_id": job_id,
                        "code": "claim_timestamp_in_future",
                        "severity": "critical",
                        "recommended_action": "check_clock_and_reconcile",
                    }
                )
            elif claimed_at < cutoff:
                issues.append(
                    {
                        "job_id": job_id,
                        "code": "expired_running_lease",
                        "severity": "warning",
                        "recommended_action": "review_lease_recovery",
                    }
                )
        elif claimed_by or claimed_at_raw:
            issues.append(
                {
                    "job_id": job_id,
                    "code": "non_running_job_has_lease_fields",
                    "severity": "critical",
                    "recommended_action": "manual_reconciliation",
                }
            )

        retry_valid = (
            attempts is not None
            and max_attempts is not None
            and max_attempts >= 1
            and attempts >= 0
            and attempts <= max_attempts
        )
        if not retry_valid:
            issues.append(
                {
                    "job_id": job_id,
                    "code": "invalid_retry_state",
                    "severity": "critical",
                    "recommended_action": "manual_reconciliation",
                }
            )
        elif status == "queued" and attempts >= max_attempts:
            issues.append(
                {
                    "job_id": job_id,
                    "code": "queued_retry_budget_exhausted",
                    "severity": "critical",
                    "recommended_action": "manual_reconciliation",
                }
            )

    if truncated:
        issues.append(
            {
                "job_id": None,
                "code": "assessment_truncated",
                "severity": "critical",
                "recommended_action": "reduce_queue_or_use_offline_recovery_check",
            }
        )

    severity_counts = {
        "critical": sum(item["severity"] == "critical" for item in issues),
        "warning": sum(item["severity"] == "warning" for item in issues),
    }
    return {
        "jobs_total": total,
        "jobs_assessed": len(jobs),
        "jobs_by_status": status_counts,
        "issues_total": len(issues),
        "issues_by_severity": severity_counts,
        "issues": issues,
        "safe_to_resume": not issues,
        "assessment_truncated": truncated,
        "read_only": True,
        "automatic_requeue": False,
        "automatic_job_creation": False,
        "automatic_mutation": False,
        "payloads_exposed": False,
        "worker_identities_exposed": False,
    }


@router.get("/api/recovery/queue")
def queue_recovery_assessment():
    from .main import queue

    backend = queue()
    try:
        lease_seconds = _job_lease_seconds()
        stats = backend.stats()
        jobs = backend.recovery_snapshot(limit=MAX_RECOVERY_JOBS)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Queue recovery assessment unavailable",
        ) from exc

    return analyze_queue_recovery(
        jobs,
        lease_seconds=lease_seconds,
        total_jobs=int(stats.get("total") or 0),
    )
