import pytest

from app.observation_graph import Observation
from app.review_evidence import is_completed_review_evidence


@pytest.mark.parametrize(
    ("status", "accepted"),
    [
        ("completed", True),
        ("success", True),
        ("reviewed", True),
        ("observed", True),
        ("queued", False),
        ("in_progress", False),
        ("failed", False),
        ("cancelled", False),
        ("skipped", False),
        ("timeout", False),
        ("", False),
    ],
)
def test_review_completion_requires_accepted_explicit_status(status, accepted):
    record = Observation(
        "review:one",
        "evidence",
        "review-recorded",
        "review-agent",
        metadata={
            "review_type": "authorization_surface_review",
            "status": status,
        },
    )

    assert is_completed_review_evidence(record) is accepted


def test_legacy_review_record_without_status_remains_compatible():
    record = Observation(
        "review:legacy",
        "evidence",
        "review-recorded",
        "review-agent",
        metadata={"review_type": "form_surface_review"},
    )

    assert is_completed_review_evidence(record) is True


def test_inconclusive_or_failed_outcome_does_not_close_gap():
    for outcome in ("failure", "inconclusive"):
        record = Observation(
            f"review:{outcome}",
            "evidence",
            "review-recorded",
            "review-agent",
            metadata={
                "review_type": "form_surface_review",
                "status": "completed",
                "outcome": outcome,
            },
        )
        assert is_completed_review_evidence(record) is False


def test_review_requires_explicit_review_type():
    record = Observation(
        "review:no-type",
        "evidence",
        "review-recorded",
        "review-agent",
        metadata={"status": "completed"},
    )

    assert is_completed_review_evidence(record) is False
