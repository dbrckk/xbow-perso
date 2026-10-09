from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .observation_graph import ObservationGraph


_TERMINAL_SCAN_STATES = frozenset({"completed", "failed", "cancelled"})

def canonical_scan_job_id(raw: object) -> str | None:
    """Validate one explicit scan-job identity shared across evidence consumers.

    Missing IDs are a separate legacy case. Reject invisible or control
    characters, including DEL and Unicode format controls, before grouping
    observations that claim to represent the same worker execution.
    """
    if not isinstance(raw, str):
        return None
    normalized = raw.strip()
    if not 0 < len(normalized) <= 128 or not all(
        char.isprintable() for char in raw
    ):
        return None
    return normalized



def canonical_scan_source(raw: object) -> str | None:
    """Accept only bounded, printable scanner labels with no path escapes.

    Provenance labels are identities, never filesystem paths or encoded text.
    """
    if not isinstance(raw, str):
        return None
    normalized = raw.strip()
    if (
        not 0 < len(normalized) <= 128
        or not all(char.isprintable() for char in raw)
        or any(char.isspace() and char != " " for char in normalized)
        # Literal escape sequences are ambiguous when source labels are logged,
        # exported or interpreted by downstream evidence processors.
        or "\\" in normalized
    ):
        return None
    return normalized


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
        job_id = canonical_scan_job_id(item.metadata.get("job_id"))
        if job_id is None:
            continue
        states_by_job.setdefault(job_id, set()).add(status)
    return frozenset(
        job_id for job_id, statuses in states_by_job.items()
        if len(statuses) > 1
    )


def plausible_scan_timeline(
    metadata: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Reject explicitly impossible scan times without inventing legacy dates.

    Timestamps must contain a UTC offset. An absent timestamp is unknown,
    not contradictory. Explicit future, malformed or reversed chronology
    cannot corroborate scan completion.
    """
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must include timezone information")
    current_time = current_time.astimezone(timezone.utc)

    def parse(key: str) -> datetime | None:
        if key not in metadata:
            return None
        value = metadata[key]
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        parsed = parsed.astimezone(timezone.utc)
        if parsed > current_time:
            return None
        return parsed

    start = parse("started_at")
    finish = parse("completed_at")
    if "started_at" in metadata and start is None:
        return False
    if "completed_at" in metadata and finish is None:
        return False
    return not (
        start is not None
        and finish is not None
        and start > finish
    )
