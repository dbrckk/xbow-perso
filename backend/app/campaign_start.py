from __future__ import annotations

from typing import Any

from .jobqueue import JobQueue
from .orchestrator import advance_campaign
from .storage import Storage


def start_via_orchestrator(
    campaign: Any,
    queue: JobQueue,
    store: Storage,
) -> dict[str, Any]:
    """Start a campaign through the bounded planner instead of a scanner shortcut."""
    result = advance_campaign(campaign, queue, store)
    job_ids = list(result.get("job_ids") or [])
    jobs = [
        job
        for job_id in job_ids
        if (job := queue.get(job_id)) is not None
    ]
    return {
        "planner": result,
        "jobs": jobs,
        "primary_job": jobs[0] if jobs else None,
    }
