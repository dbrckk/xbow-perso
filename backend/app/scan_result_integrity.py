from __future__ import annotations

from .observation_graph import ObservationGraph


_TERMINAL_SCAN_STATES = frozenset({"completed", "failed", "cancelled"})


def conflicting_scan_terminal_job_ids(graph: ObservationGraph) -> frozenset[str]:
    """Identify one job reporting incompatible terminal scan outcomes.

    Only explicit bounded job IDs establish a cross-observation identity.
    A queued/retry event is not a terminal contradiction.
    """
    states_by_job: dict[str, set[str]] = {}
    for item in graph.by_kind("evidence"):
        if item.metadata.get("phase") != "scan":
            continue
        status = item.metadata.get("status")
        if not isinstance(status, str) or status not in _TERMINAL_SCAN_STATES:
            continue
        raw_id = item.metadata.get("job_id")
        if (
            not isinstance(raw_id, str)
            or not 0 < len(raw_id.strip()) <= 128
            or any(ord(char) < 32 for char in raw_id)
        ):
            continue
        states_by_job.setdefault(raw_id.strip(), set()).add(status)
    return frozenset(
        job_id for job_id, statuses in states_by_job.items()
        if len(statuses) > 1
    )
