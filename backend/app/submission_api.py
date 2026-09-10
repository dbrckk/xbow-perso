from __future__ import annotations

from collections import Counter
from typing import Literal

from fastapi import APIRouter, HTTPException

from .report_approval import (
    approval_event_from_storage,
    approval_status_from_storage,
    revocation_event,
)
from .storage import ArtifactIntegrityError
from .submission_state import assert_submission_allowed, submission_event, submission_status

router = APIRouter()


def _context(campaign_id: str):
    from .main import assert_campaign_record, storage

    campaign, version = assert_campaign_record(campaign_id)
    return campaign, version, storage()


def _verified_report(campaign, store, artifact_id: str) -> dict:
    try:
        artifact, _content = store.read_artifact(campaign.id, artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report artifact not found") from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(status_code=409, detail="Report artifact integrity verification failed") from exc
    if artifact.get("kind") != "report":
        raise HTTPException(status_code=409, detail="Artifact is not a report")
    return artifact


def _save(campaign, version: int) -> None:
    from .main import save_campaign

    save_campaign(campaign, expected_version=version)


@router.get("/api/campaigns/{campaign_id}/reports/submission-states")
def list_submission_states(campaign_id: str):
    campaign, _version, store = _context(campaign_id)
    report_ids = [
        artifact["id"]
        for artifact in store.list_artifacts(campaign.id)
        if artifact.get("kind") == "report"
    ]
    states = [
        submission_status(campaign, _verified_report(campaign, store, artifact_id)).to_dict()
        for artifact_id in report_ids
    ]
    counts = Counter(item["state"] for item in states)
    return {
        "campaign_id": campaign.id,
        "reports": states,
        "counts": {
            state: counts.get(state, 0)
            for state in ("draft", "review_required", "approved", "submitted")
        },
        "total": len(states),
    }


@router.get("/api/campaigns/{campaign_id}/reports/{artifact_id}/submission-state")
def get_submission_state(campaign_id: str, artifact_id: str):
    campaign, _version, store = _context(campaign_id)
    artifact = _verified_report(campaign, store, artifact_id)
    return submission_status(campaign, artifact).to_dict()


@router.post("/api/campaigns/{campaign_id}/reports/{artifact_id}/approve")
def approve_report(campaign_id: str, artifact_id: str, reviewer: str):
    from .main import utcnow

    campaign, version, store = _context(campaign_id)
    artifact = _verified_report(campaign, store, artifact_id)
    try:
        current = approval_status_from_storage(campaign, store, artifact_id)
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("reviewer is required")
        if current.approved and current.reviewer == reviewer:
            return submission_status(campaign, artifact).to_dict()
        campaign.events.append(approval_event_from_storage(campaign, store, artifact_id, reviewer, utcnow()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    campaign.updated_at = utcnow()
    _save(campaign, version)
    return submission_status(campaign, artifact).to_dict()


@router.post("/api/campaigns/{campaign_id}/reports/{artifact_id}/revoke-approval")
def revoke_report_approval(campaign_id: str, artifact_id: str, reviewer: str):
    from .main import utcnow

    campaign, version, store = _context(campaign_id)
    artifact = _verified_report(campaign, store, artifact_id)
    reviewer = reviewer.strip()
    if not reviewer:
        raise HTTPException(status_code=400, detail="reviewer is required")
    relevant = [
        event
        for event in campaign.events
        if event.get("artifact_id") == artifact_id
        and event.get("type") in {"report_approved", "report_approval_revoked"}
    ]
    if relevant and relevant[-1].get("type") == "report_approval_revoked":
        return submission_status(campaign, artifact).to_dict()
    campaign.events.append(revocation_event(artifact_id, reviewer, utcnow()))
    campaign.updated_at = utcnow()
    _save(campaign, version)
    return submission_status(campaign, artifact).to_dict()


@router.post("/api/campaigns/{campaign_id}/reports/{artifact_id}/mark-submitted")
def mark_report_submitted(
    campaign_id: str,
    artifact_id: str,
    actor: str,
    platform: Literal["generic", "hackerone", "bugcrowd"] = "generic",
):
    from .main import utcnow

    campaign, version, store = _context(campaign_id)
    artifact = _verified_report(campaign, store, artifact_id)
    current = submission_status(campaign, artifact)
    actor = actor.strip()
    if current.state == "submitted":
        if current.submitted_by == actor and current.platform == platform:
            return current.to_dict()
        raise HTTPException(status_code=409, detail="Report is already marked submitted with different metadata")
    try:
        assert_submission_allowed(campaign, artifact)
        campaign.events.append(submission_event(artifact_id, actor, platform, utcnow()))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    campaign.updated_at = utcnow()
    _save(campaign, version)
    return submission_status(campaign, artifact).to_dict()
