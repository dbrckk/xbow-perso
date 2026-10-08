from __future__ import annotations

from typing import Any, Mapping


_COMPLETED_REVIEW_STATES = frozenset(
    {"completed", "success", "reviewed", "observed"}
)


def is_completed_review_evidence(observation: Any) -> bool:
    """Credit a review only when explicit execution fields support completion.

    Historical review records have no status or outcome metadata. They remain
    compatible, but explicit failure, cancellation, queueing, or inconclusive
    values must never close an evidence-coverage gap.
    """
    metadata = getattr(observation, "metadata", None)
    if not isinstance(metadata, Mapping):
        return False
    review_type = metadata.get("review_type")
    if not isinstance(review_type, str) or not review_type.strip():
        return False

    for field in ("status", "outcome"):
        value = metadata.get(field)
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or value.strip().lower() not in _COMPLETED_REVIEW_STATES
        ):
            return False
    return True
