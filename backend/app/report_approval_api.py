from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from .campaign_audit import append_campaign_event
from .report_approval import (
    approval_event_from_storage,
    approval_status_from_storage,
    revocation_event,
)
from .storage import ArtifactIntegrityError


router = APIRouter()


class ReportApprovalInput(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)

    @field_validator("reviewer")
    @classmethod
    def normalize_reviewer(cls, value: str) -> str:
        reviewer = value.strip()
        if not reviewer:
            raise ValueError("reviewer must not be blank")
        return reviewer


def _status(campaign_id: str, artifact_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    try:
        return approval_status_from_storage(campaign, storage(), artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report artifact not found") from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Report artifact integrity verification failed: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/campaigns/{campaign_id}/reports/{artifact_id}/approval")
def report_approval_status(campaign_id: str, artifact_id: str):
    return {
        **_status(campaign_id, artifact_id).to_dict(),
        "read_only": True,
    }


@router.post("/api/campaigns/{campaign_id}/reports/{artifact_id}/approval")
def approve_report(
    campaign_id: str,
    artifact_id: str,
    payload: ReportApprovalInput,
):
    from .main import (
        _reject_cancelled_campaign,
        assert_campaign_record,
        assert_campaign_exists,
        save_campaign,
        storage,
        utcnow,
    )

    campaign, version = assert_campaign_record(campaign_id)
    _reject_cancelled_campaign(campaign)
    store = storage()

    try:
        current = approval_status_from_storage(campaign, store, artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report artifact not found") from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Report artifact integrity verification failed: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if current.approved and current.reviewer == payload.reviewer:
        return current.to_dict()

    try:
        event = approval_event_from_storage(
            campaign,
            store,
            artifact_id,
            payload.reviewer,
            utcnow(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report artifact not found") from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Report artifact integrity verification failed: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    append_campaign_event(campaign.events, event)
    campaign.updated_at = utcnow()
    save_campaign(campaign, expected_version=version)

    latest = assert_campaign_exists(campaign_id)
    try:
        return approval_status_from_storage(latest, storage(), artifact_id).to_dict()
    except ArtifactIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Report artifact integrity verification failed: {exc}",
        ) from exc


@router.post("/api/campaigns/{campaign_id}/reports/{artifact_id}/approval/revoke")
def revoke_report_approval(
    campaign_id: str,
    artifact_id: str,
    payload: ReportApprovalInput,
):
    from .main import (
        _reject_cancelled_campaign,
        assert_campaign_record,
        assert_campaign_exists,
        save_campaign,
        storage,
        utcnow,
    )

    campaign, version = assert_campaign_record(campaign_id)
    _reject_cancelled_campaign(campaign)
    store = storage()

    try:
        approval_status_from_storage(campaign, store, artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report artifact not found") from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Report artifact integrity verification failed: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    relevant = [
        event
        for event in campaign.events
        if event.get("artifact_id") == artifact_id
        and event.get("type") in {"report_approved", "report_approval_revoked"}
    ]
    if not relevant or relevant[-1].get("type") != "report_approved":
        raise HTTPException(status_code=409, detail="Report has no active approval to revoke")

    append_campaign_event(
        campaign.events,
        revocation_event(artifact_id, payload.reviewer, utcnow()),
    )
    campaign.updated_at = utcnow()
    save_campaign(campaign, expected_version=version)

    latest = assert_campaign_exists(campaign_id)
    try:
        return approval_status_from_storage(latest, storage(), artifact_id).to_dict()
    except ArtifactIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Report artifact integrity verification failed: {exc}",
        ) from exc
