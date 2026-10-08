from __future__ import annotations

from typing import Any, Mapping


_COMPLETED_REVIEW_STATES = frozenset({"completed", "reviewed"})
_SUCCESSFUL_REVIEW_OUTCOMES = frozenset(
    {"completed", "success", "reviewed", "observed"}
)


def is_completed_review_evidence(observation: Any) -> bool:
    """Credit a review only with explicit terminal completion metadata.

    Align with no-finding recovery's terminal review policy: missing,
    queued, cancelled, failed or inconclusive reviews do not close coverage
    gaps. Additional outcome metadata may not contradict completion.
    """
    metadata = getattr(observation, "metadata", None)
    if not isinstance(metadata, Mapping):
        return False
    review_type = metadata.get("review_type")
    if not isinstance(review_type, str) or not review_type.strip():
        return False

    status = metadata.get("status")
    if (
        not isinstance(status, str)
        or status.strip().lower() not in _COMPLETED_REVIEW_STATES
    ):
        return False
    outcome = metadata.get("outcome")
    if outcome is not None and (
        not isinstance(outcome, str)
        or outcome.strip().lower() not in _SUCCESSFUL_REVIEW_OUTCOMES
    ):
        return False
    return True
