from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, field_validator, model_validator

from .hackerone_client import (
    HackerOneClient,
    HackerOneClientError,
    fetch_hackerone_program_snapshot,
    load_hackerone_credentials,
)

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
    remote_handle: str | None = Field(default=None, min_length=1, max_length=128)
    remote_snapshot_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def remote_binding_must_be_complete(self):
        if (self.remote_handle is None) != (self.remote_snapshot_sha256 is None):
            raise ValueError("remote_handle and remote_snapshot_sha256 must be supplied together")
        return self


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


def _verify_remote_binding(payload: HackerOneRulesPreviewInput) -> dict[str, Any] | None:
    if payload.remote_handle is None:
        return None
    try:
        snapshot = fetch_hackerone_program_snapshot(payload.remote_handle)
    except HackerOneClientError as exc:
        raise _upstream_error(exc) from exc

    if snapshot.snapshot_sha256 != payload.remote_snapshot_sha256:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne remote snapshot changed; review again",
                "reason": "stale_hackerone_snapshot",
            },
        )
    if _json_sha256(snapshot.document) != _json_sha256(payload.document):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne scope document does not match the verified remote snapshot",
                "reason": "hackerone_snapshot_document_mismatch",
            },
        )
    return {
        "handle": snapshot.handle,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "verified": True,
    }


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



def _upstream_error(exc: HackerOneClientError) -> HTTPException:
    if exc.status_code in {401, 403}:
        return HTTPException(status_code=502, detail="HackerOne upstream authentication failed")
    if exc.status_code == 429 or (exc.status_code is not None and exc.status_code >= 500):
        return HTTPException(status_code=503, detail="HackerOne upstream temporarily unavailable")
    return HTTPException(status_code=502, detail="HackerOne upstream request failed")


def _program_list_item(resource: Any) -> dict[str, Any]:
    if not isinstance(resource, dict):
        raise HackerOneClientError("HackerOne program list contains an invalid resource")
    attributes = resource.get("attributes")
    if not isinstance(attributes, dict):
        raise HackerOneClientError("HackerOne program list contains invalid attributes")
    handle = attributes.get("handle")
    name = attributes.get("name")
    if not isinstance(handle, str) or not handle or not isinstance(name, str) or not name:
        raise HackerOneClientError("HackerOne program list contains invalid identity fields")
    return {
        "handle": handle,
        "name": name,
        "submission_state": attributes.get("submission_state"),
        "state": attributes.get("state"),
        "offers_bounties": attributes.get("offers_bounties"),
        "gold_standard_safe_harbor": attributes.get("gold_standard_safe_harbor"),
    }


@router.get("/api/imports/hackerone/connection")
def hackerone_connection():
    try:
        load_hackerone_credentials()
    except HackerOneClientError:
        return {"provider": "hackerone", "configured": False}
    return {"provider": "hackerone", "configured": True}


@router.get("/api/imports/hackerone/programs")
def list_hackerone_programs():
    try:
        resources = HackerOneClient().get_all_pages("hackers/programs")
        programs = [_program_list_item(resource) for resource in resources]
    except HackerOneClientError as exc:
        raise _upstream_error(exc) from exc
    programs.sort(key=lambda item: (str(item["name"]).lower(), str(item["handle"])))
    return {"provider": "hackerone", "programs": programs}


@router.get("/api/imports/hackerone/programs/{handle}/snapshot")
def get_hackerone_program_snapshot(handle: str):
    try:
        snapshot = fetch_hackerone_program_snapshot(handle)
    except HackerOneClientError as exc:
        raise _upstream_error(exc) from exc
    return {
        "provider": "hackerone",
        "handle": snapshot.handle,
        "program": snapshot.program,
        "document": snapshot.document,
        "scope_exclusions": list(snapshot.scope_exclusions),
        "preview": snapshot.preview,
        "snapshot_sha256": snapshot.snapshot_sha256,
    }


@router.post("/api/imports/hackerone/rules-preview")
def preview_hackerone_rules(payload: HackerOneRulesPreviewInput):
    """Preview exact executable rules without persisting or starting a campaign."""

    from .hackerone_scope_import import HackerOneScopeImportError, import_hackerone_structured_scope

    remote_binding = _verify_remote_binding(payload)
    try:
        preview = import_hackerone_structured_scope(payload.document)
        policy = _policy_from_input(payload.policy)
        rules = preview.to_program_rules(policy=policy)
    except HackerOneScopeImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = {
        "provider": "hackerone",
        "complete": preview.complete,
        "requires_review": True,
        "persisted": False,
        "campaign_created": False,
        "policy_snapshot": policy.to_snapshot(),
        "rules": rules.model_dump(mode="json"),
    }
    if remote_binding is not None:
        result["remote_binding"] = remote_binding
    return result


@router.post("/api/imports/hackerone/campaigns")
def admit_hackerone_campaign(payload: HackerOneCampaignAdmissionInput):
    from .campaign_audit import append_campaign_event
    from .hackerone_scope_import import HackerOneScopeImportError, import_hackerone_structured_scope
    from .job_provenance import policy_snapshot_fingerprint
    from .main import Campaign, CampaignState, TargetInput, save_campaign, utcnow

    remote_binding = _verify_remote_binding(payload)
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
    binding_payload = {
        "provider": "hackerone",
        "mode": "conservative",
        "policy_snapshot_sha256": policy_snapshot_sha256,
        "campaign_policy_fingerprint": campaign_policy_fingerprint,
    }
    if remote_binding is not None:
        binding_payload["remote_binding"] = remote_binding
    binding_fingerprint = _json_sha256(binding_payload)

    append_campaign_event(
        campaign.events,
        {"type": "campaign_created", "at": utcnow()},
    )
    binding_event = {
        "type": "hackerone_policy_bound",
        "at": utcnow(),
        "provider": "hackerone",
        "mode": "conservative",
        "policy_snapshot": policy_snapshot,
        "policy_snapshot_sha256": policy_snapshot_sha256,
        "campaign_policy_fingerprint": campaign_policy_fingerprint,
        "binding_fingerprint": binding_fingerprint,
    }
    if remote_binding is not None:
        binding_event["remote_binding"] = remote_binding
    append_campaign_event(campaign.events, binding_event)
    save_campaign(campaign, expected_version=0)

    policy_binding = {
        "mode": "conservative",
        "policy_snapshot_sha256": policy_snapshot_sha256,
        "binding_fingerprint": binding_fingerprint,
    }
    if remote_binding is not None:
        policy_binding["remote_binding"] = remote_binding
    return {
        "provider": "hackerone",
        "campaign_created": True,
        "campaign": campaign.model_dump(mode="json"),
        "policy_binding": policy_binding,
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
