from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .report_approval import approval_status

SubmissionState = Literal["draft", "review_required", "approved", "submitted"]


@dataclass(frozen=True)
class SubmissionStatus:
    artifact_id: str
    state: SubmissionState
    approved: bool
    stale: bool
    reviewer: str | None
    submitted_at: str | None
    submitted_by: str | None
    platform: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def submission_event(artifact_id: str, actor: str, platform: str, at: str) -> dict[str, Any]:
    actor = actor.strip()
    platform = platform.strip()
    if not actor:
        raise ValueError("submission actor is required")
    if not platform:
        raise ValueError("submission platform is required")
    return {
        "type": "report_submitted",
        "artifact_id": artifact_id,
        "actor": actor,
        "platform": platform,
        "at": at,
    }


def submission_status(campaign: Any, artifact: dict[str, Any]) -> SubmissionStatus:
    if artifact.get("kind") != "report":
        raise ValueError("only report artifacts have submission state")

    approval = approval_status(campaign, artifact)
    relevant_approval_events = [
        event
        for event in campaign.events
        if event.get("artifact_id") == artifact["id"]
        and event.get("type") in {"report_approved", "report_approval_revoked"}
    ]
    revoked = bool(relevant_approval_events) and relevant_approval_events[-1].get("type") == "report_approval_revoked"
    submissions = [
        event
        for event in campaign.events
        if event.get("type") == "report_submitted" and event.get("artifact_id") == artifact["id"]
    ]

    if not approval.approved:
        state: SubmissionState = "review_required" if submissions or approval.stale or revoked else "draft"
        return SubmissionStatus(
            artifact_id=artifact["id"],
            state=state,
            approved=False,
            stale=approval.stale,
            reviewer=approval.reviewer,
            submitted_at=None,
            submitted_by=None,
            platform=None,
        )

    if submissions:
        latest = submissions[-1]
        return SubmissionStatus(
            artifact_id=artifact["id"],
            state="submitted",
            approved=True,
            stale=False,
            reviewer=approval.reviewer,
            submitted_at=latest.get("at"),
            submitted_by=latest.get("actor"),
            platform=latest.get("platform"),
        )

    return SubmissionStatus(
        artifact_id=artifact["id"],
        state="approved",
        approved=True,
        stale=False,
        reviewer=approval.reviewer,
        submitted_at=None,
        submitted_by=None,
        platform=None,
    )


def assert_submission_allowed(campaign: Any, artifact: dict[str, Any]) -> SubmissionStatus:
    status = submission_status(campaign, artifact)
    if status.state != "approved":
        raise ValueError("report submission requires current human approval")
    return status
