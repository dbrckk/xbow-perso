from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictBool

from .hackerone_scope_import import (
    HackerOneProgramPolicy,
    HackerOneScopeImportError,
    import_hackerone_structured_scope,
)

router = APIRouter()


class HackerOneProgramPolicyInput(BaseModel):
    authorization_reference: str = Field(min_length=3, max_length=2048)
    automated_scanning: StrictBool
    max_requests_per_second: float = Field(gt=0, le=20)


class HackerOneRulesPreviewInput(BaseModel):
    document: dict[str, Any]
    policy: HackerOneProgramPolicyInput


@router.post("/api/imports/hackerone/rules-preview")
def preview_hackerone_rules(payload: HackerOneRulesPreviewInput):
    """Preview exact executable rules without persisting or starting a campaign."""

    try:
        preview = import_hackerone_structured_scope(payload.document)
        policy = HackerOneProgramPolicy(
            authorization_reference=payload.policy.authorization_reference,
            automated_scanning=payload.policy.automated_scanning,
            max_requests_per_second=payload.policy.max_requests_per_second,
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
        "rules": rules.model_dump(mode="json"),
    }
