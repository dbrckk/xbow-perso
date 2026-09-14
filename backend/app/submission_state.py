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
    artifact_id = artifact_id.strip()
    actor = actor.strip()
    platform = platform.strip()
    at = at.strip()
    if not artifact_id:
        raise ValueError("submission artifact id is required")
    if not actor:
        raise ValueError("submission actor is required")
    if not platform:
        raise ValueError("submission platform is required")
    if not at:
        raise ValueError("submission timestamp is required")
    return {
        "type": "report_submitted",
        "artifact_id": artifact_id,
        "actor": actor,
        "platform": platform,
        "at": at,
    }


def _approval_events(campaign: Any, artifact_id: str) -> list[tuple[int, dict[str, Any]]]:
    return [
        (index, event)
        for index, event in enumerate(campaign.events)
        if event.get("artifact_id") == artifact_id
        and event.get("type") in {"report_approved", "report_approval_revoked"}
    ]


def submission_status(campaign: Any, artifact: dict[str, Any]) -> SubmissionStatus:
    if artifact.get("kind") != "report":
        raise ValueError("only report artifacts have submission state")

    artifact_id = artifact["id"]
    approval = approval_status(campaign, artifact)
    approval_events = _approval_events(campaign, artifact_id)
    revoked = bool(approval_events) and approval_events[-1][1].get("type") == "report_approval_revoked"

    all_submissions = [
        (index, event)
        for index, event in enumerate(campaign.events)
        if event.get("type") == "report_submitted" and event.get("artifact_id") == artifact_id
    ]

    if not approval.approved:
        state: SubmissionState = "review_required" if all_submissions or approval.stale or revoked else "draft"
        return SubmissionStatus(
            artifact_id=artifact_id,
            state=state,
            approved=False,
            stale=approval.stale,
            reviewer=approval.reviewer,
            submitted_at=None,
            submitted_by=None,
            platform=None,
        )

    latest_approval_index = approval_events[-1][0] if approval_events else -1
    current_cycle_submissions = [
        event for index, event in all_submissions if index > latest_approval_index
    ]
    if current_cycle_submissions:
        latest = current_cycle_submissions[-1]
        return SubmissionStatus(
            artifact_id=artifact_id,
            state="submitted",
            approved=True,
            stale=False,
            reviewer=approval.reviewer,
            submitted_at=latest.get("at"),
            submitted_by=latest.get("actor"),
            platform=latest.get("platform"),
        )

    return SubmissionStatus(
        artifact_id=artifact_id,
        state="approved",
        approved=True,
        stale=False,
        reviewer=approval.reviewer,
        submitted_at=None,
        submitted_by=None,
        platform=None,
    )


def _quality_gate_value(gate: Any, field: str, default: Any = None) -> Any:
    if isinstance(gate, dict):
        return gate.get(field, default)
    return getattr(gate, field, default)


def assert_submission_allowed(
    campaign: Any,
    artifact: dict[str, Any],
    quality_gates: list[Any],
) -> SubmissionStatus:
    """Require current human approval plus verified report quality for submission.

    This function is a local governance gate only. It does not submit externally.
    """
    status = submission_status(campaign, artifact)
    if status.state != "approved":
        raise ValueError("report submission requires current human approval")

    confirmed_ids = {
        str(finding.id)
        for finding in campaign.findings
        if getattr(finding, "status", None) == "confirmed"
    }
    by_id = {
        str(_quality_gate_value(gate, "finding_id", "")): gate
        for gate in quality_gates
        if str(_quality_gate_value(gate, "finding_id", ""))
    }

    missing = sorted(confirmed_ids - set(by_id))
    if missing:
        raise ValueError("report submission blocked: missing quality gate coverage")

    for finding_id in sorted(confirmed_ids):
        gate = by_id[finding_id]
        grade = str(_quality_gate_value(gate, "grade", ""))
        submission_ready = bool(
            _quality_gate_value(gate, "submission_ready", False)
        )
        checks = _quality_gate_value(gate, "checks", {}) or {}
        provenance_complete = bool(checks.get("provenance_complete"))
        provenance_verified = bool(checks.get("provenance_verified"))

        if grade not in {"A", "B"}:
            raise ValueError(
                "report submission blocked: quality grade below submission threshold"
            )
        if not submission_ready:
            raise ValueError(
                "report submission blocked: finding is not submission-ready"
            )
        if not provenance_complete:
            raise ValueError(
                "report submission blocked: provenance is incomplete"
            )
        if not provenance_verified:
            raise ValueError(
                "report submission blocked: provenance verification failed"
            )

    return status
