from __future__ import annotations

import os
from typing import Any


def _positive_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def build_worker_watchdog(metrics: dict[str, Any]) -> dict[str, Any]:
    """Evaluate aggregate worker health without exposing jobs, targets, or payloads."""
    max_queue_age = _positive_int(
        "XBOW_WATCHDOG_MAX_QUEUE_AGE_SECONDS", 600, minimum=30, maximum=86400
    )
    max_lease_age = _positive_int(
        "XBOW_WATCHDOG_MAX_RUNNING_LEASE_AGE_SECONDS",
        21600,
        minimum=60,
        maximum=86400,
    )
    max_failed = _positive_int(
        "XBOW_WATCHDOG_MAX_FAILED_JOBS", 5, minimum=0, maximum=100000
    )

    issues: list[dict[str, Any]] = []
    queued_age = metrics.get("oldest_queued_age_seconds")
    lease_age = metrics.get("oldest_running_lease_age_seconds")
    failed = int((metrics.get("jobs_by_status") or {}).get("failed") or 0)

    if queued_age is not None and int(queued_age) > max_queue_age:
        issues.append({"code": "queue_stalled", "severity": "warning"})
    if lease_age is not None and int(lease_age) > max_lease_age:
        issues.append({"code": "running_lease_stale", "severity": "error"})
    if failed > max_failed:
        issues.append({"code": "failed_job_budget_exceeded", "severity": "warning"})

    status = (
        "error"
        if any(item["severity"] == "error" for item in issues)
        else "warning"
        if issues
        else "ok"
    )
    return {
        "status": status,
        "issues": issues,
        "thresholds": {
            "max_queue_age_seconds": max_queue_age,
            "max_running_lease_age_seconds": max_lease_age,
            "max_failed_jobs": max_failed,
        },
        "read_only": True,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
