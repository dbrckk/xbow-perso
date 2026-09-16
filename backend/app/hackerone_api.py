from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, field_validator

router = APIRouter()


class HackerOneProgramPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_reference: str = Field(min_length=3, max_length=2048)
    policy_version: str = Field(min_length=1, max_length=256)
    reviewed_at: datetime
    reviewed_by: str = Field(min_length=1, max_length=256)
    safe_harbor_confirmed: StrictBool
    automated_scanning: StrictBool
    max_requests_per_second: float = Field(gt=0, le=20)
    test_account_required: StrictBool
    test_account_constraints: str = Field(max_length=4096)
    additional_restrictions: list[str] = Field(max_length=100)
    program_notes: str = Field(max_length=8192)

    @field_validator("reviewed_at")
    @classmethod
    def reviewed_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reviewed_at must include a timezone")
        return value

    @field_validator("max_requests_per_second", mode="before")
    @classmethod
    def request_rate_must_be_explicit_number(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("max_requests_per_second must be an explicit number")
        return value


class HackerOneRulesPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: dict[str, Any]
    policy: HackerOneProgramPolicyInput


class HackerOneCampaignTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    primary_url: HttpUrl


class HackerOneCampaignAdmissionInput(HackerOneRulesPreviewInput):
    target: HackerOneCampaignTargetInput


def _policy_from_input(payload: HackerOneProgramPolicyInput):
    from .hackerone_scope_import import HackerOneProgramPolicy

    return HackerOneProgramPolicy(
        authorization_reference=payload.authorization_reference,
        policy_version=payload.policy_version,
        reviewed_at=payload.reviewed_at.isoformat(),
        reviewed_by=payload.reviewed_by,
        safe_harbor_confirmed=payload.safe_harbor_confirmed,
        automated_scanning=payload.automated_scanning,
        max_requests_per_second=payload.max_requests_per_second,
        test_account_required=payload.test_account_required,
        test_account_constraints=payload.test_account_constraints,
        additional_restrictions=tuple(payload.additional_restrictions),
        program_notes=payload.program_notes,
    )


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _conservative_admission_reason(policy: Any) -> str | None:
    if not policy.safe_harbor_confirmed:
        return "safe_harbor_required"
    if not policy.automated_scanning:
        return "automated_scanning_not_authorized"
    if policy.test_account_required:
        return "test_account_workflow_not_supported"
    if policy.test_account_constraints:
        return "test_account_constraints_not_supported"
    if policy.additional_restrictions:
        return "additional_restrictions_require_manual_enforcement"
    return None


@router.post("/api/imports/hackerone/rules-preview")
def preview_hackerone_rules(payload: HackerOneRulesPreviewInput):
    """Preview exact executable rules without persisting or starting a campaign."""

    from .hackerone_scope_import import HackerOneScopeImportError, import_hackerone_structured_scope

    try:
        preview = import_hackerone_structured_scope(payload.document)
        policy = _policy_from_input(payload.policy)
        rules = preview.to_program_rules(policy=policy)
    except HackerOneScopeImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "provider": "hackerone",
        "complete": preview.complete,
        "requires_review": True,
        "persisted": False,
        "campaign_created": False,
        "policy_snapshot": policy.to_snapshot(),
        "rules": rules.model_dump(mode="json"),
    }


@router.post("/api/imports/hackerone/campaigns")
def admit_hackerone_campaign(payload: HackerOneCampaignAdmissionInput):
    from .campaign_audit import append_campaign_event
    from .hackerone_scope_import import HackerOneScopeImportError, import_hackerone_structured_scope
    from .job_provenance import policy_snapshot_fingerprint
    from .main import Campaign, CampaignState, TargetInput, save_campaign, utcnow

    try:
        preview = import_hackerone_structured_scope(payload.document)
        policy = _policy_from_input(payload.policy)
        reason = _conservative_admission_reason(policy)
        if reason:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "HackerOne conservative admission blocked",
                    "reason": reason,
                },
            )
        rules = preview.to_program_rules(policy=policy)
        target = TargetInput(
            name=payload.target.name,
            primary_url=payload.target.primary_url,
            rules=rules,
        )
    except HTTPException:
        raise
    except (HackerOneScopeImportError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    campaign = Campaign(target=target, state=CampaignState.ready)
    policy_snapshot = policy.to_snapshot()
    policy_snapshot_sha256 = _json_sha256(policy_snapshot)
    campaign_policy_fingerprint = policy_snapshot_fingerprint(campaign)
    binding_fingerprint = _json_sha256(
        {
            "provider": "hackerone",
            "mode": "conservative",
            "policy_snapshot_sha256": policy_snapshot_sha256,
            "campaign_policy_fingerprint": campaign_policy_fingerprint,
        }
    )

    append_campaign_event(
        campaign.events,
        {"type": "campaign_created", "at": utcnow()},
    )
    append_campaign_event(
        campaign.events,
        {
            "type": "hackerone_policy_bound",
            "at": utcnow(),
            "provider": "hackerone",
            "mode": "conservative",
            "policy_snapshot": policy_snapshot,
            "policy_snapshot_sha256": policy_snapshot_sha256,
            "campaign_policy_fingerprint": campaign_policy_fingerprint,
            "binding_fingerprint": binding_fingerprint,
        },
    )
    save_campaign(campaign, expected_version=0)

    return {
        "provider": "hackerone",
        "campaign_created": True,
        "campaign": campaign.model_dump(mode="json"),
        "policy_binding": {
            "mode": "conservative",
            "policy_snapshot_sha256": policy_snapshot_sha256,
            "binding_fingerprint": binding_fingerprint,
        },
    }


@router.post("/api/imports/hackerone/campaigns/launch")
def launch_hackerone_campaign(payload: HackerOneCampaignAdmissionInput):
    """Admit a reviewed HackerOne policy and start it in one authenticated mutation."""

    from .main import assert_campaign_exists, start_campaign

    admitted = admit_hackerone_campaign(payload)
    campaign_id = admitted["campaign"]["id"]
    started = start_campaign(campaign_id)
    campaign = assert_campaign_exists(campaign_id)
    return {
        **admitted,
        "campaign": campaign.model_dump(mode="json"),
        "start": started,
    }
