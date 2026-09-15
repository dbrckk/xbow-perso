from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

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


@router.post("/api/imports/hackerone/rules-preview")
def preview_hackerone_rules(payload: HackerOneRulesPreviewInput):
    """Preview exact executable rules without persisting or starting a campaign."""

    from .hackerone_scope_import import (
        HackerOneProgramPolicy,
        HackerOneScopeImportError,
        import_hackerone_structured_scope,
    )

    try:
        preview = import_hackerone_structured_scope(payload.document)
        policy = HackerOneProgramPolicy(
            authorization_reference=payload.policy.authorization_reference,
            policy_version=payload.policy.policy_version,
            reviewed_at=payload.policy.reviewed_at.isoformat(),
            reviewed_by=payload.policy.reviewed_by,
            safe_harbor_confirmed=payload.policy.safe_harbor_confirmed,
            automated_scanning=payload.policy.automated_scanning,
            max_requests_per_second=payload.policy.max_requests_per_second,
            test_account_required=payload.policy.test_account_required,
            test_account_constraints=payload.policy.test_account_constraints,
            additional_restrictions=tuple(payload.policy.additional_restrictions),
            program_notes=payload.policy.program_notes,
        )
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
def admit_hackerone_campaign(payload: HackerOneRulesPreviewInput):
    raise HTTPException(status_code=501, detail="HackerOne conservative admission is not implemented")
