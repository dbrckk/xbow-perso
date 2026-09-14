from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


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


def analyze_queue_recovery(
    jobs: list[dict[str, Any]],
    *,
    lease_seconds: int,
    audit_results: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a read-only queue recovery assessment.

    The assessment never changes queue state and never creates/requeues work.
    It is intended for post-restore verification and operator reconciliation.
    """
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(seconds=lease_seconds)
    audit_results = audit_results or {}

    issues: list[dict[str, Any]] = []
    status_counts = {
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "unknown": 0,
    }

    for job in jobs:
        job_id = str(job.get("id") or "")
        status = str(job.get("status") or "unknown")
        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts["unknown"] += 1

        claimed_by = job.get("claimed_by")
        claimed_at_raw = job.get("claimed_at")
        claimed_at = _parse_timestamp(claimed_at_raw)
        attempts = int(job.get("attempts") or 0)
        max_attempts = int(job.get("max_attempts") or 0)

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

        if max_attempts < 1 or attempts < 0 or attempts > max_attempts:
            issues.append(
                {
                    "job_id": job_id,
                    "code": "invalid_retry_state",
                    "severity": "critical",
                    "recommended_action": "manual_reconciliation",
                }
            )

        audit = audit_results.get(job_id)
        if audit is not None and not bool(audit.get("valid")):
            issues.append(
                {
                    "job_id": job_id,
                    "code": "transition_audit_invalid",
                    "severity": "critical",
                    "recommended_action": "manual_reconciliation",
                }
            )

    severity_counts = {
        "critical": sum(item["severity"] == "critical" for item in issues),
        "warning": sum(item["severity"] == "warning" for item in issues),
    }
    plan = [
        {
            "job_id": item["job_id"],
            "issue": item["code"],
            "action": item["recommended_action"],
        }
        for item in issues
    ]

    return {
        "jobs_total": len(jobs),
        "jobs_by_status": status_counts,
        "issues_total": len(issues),
        "issues_by_severity": severity_counts,
        "issues": issues,
        "reconciliation_plan": plan,
        "safe_to_resume": not issues,
        "read_only": True,
        "automatic_requeue": False,
        "automatic_job_creation": False,
        "automatic_mutation": False,
    }
