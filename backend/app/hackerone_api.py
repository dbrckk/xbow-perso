from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, field_validator, model_validator

from .hackerone_client import (
    HackerOneClient,
    HackerOneClientError,
    fetch_hackerone_program_snapshot,
    load_hackerone_credentials,
)
from .hackerone_needs_info import render_needs_more_info_draft
from .hackerone_report_tracking import (
    latest_remote_submission,
    project_remote_report_status,
    remote_submission_for_artifact,
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


class HackerOneReportSubmissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=120)
    confirm_submission: Literal[True]

    @field_validator("actor")
    @classmethod
    def normalize_actor(cls, value: str) -> str:
        actor = value.strip()
        if not actor:
            raise ValueError("actor must not be blank")
        return actor


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


def _hackerone_submission_enabled() -> bool:
    import os

    raw = (os.getenv("XBOW_ENABLE_HACKERONE_SUBMISSION") or "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise HTTPException(
        status_code=503,
        detail="XBOW_ENABLE_HACKERONE_SUBMISSION must be a boolean",
    )


def _verified_remote_team_handle(campaign) -> str:
    for event in reversed(campaign.events):
        if event.get("type") != "hackerone_policy_bound":
            continue
        binding = event.get("remote_binding")
        if (
            isinstance(binding, dict)
            and binding.get("verified") is True
            and isinstance(binding.get("handle"), str)
            and binding["handle"].strip()
        ):
            return binding["handle"].strip()
        break
    raise HTTPException(
        status_code=409,
        detail="HackerOne external submission requires a verified remote program binding",
    )


def _unresolved_hackerone_attempt(campaign, artifact_id: str) -> dict[str, Any] | None:
    attempts = [
        (index, event)
        for index, event in enumerate(campaign.events)
        if event.get("type") == "hackerone_submission_attempted"
        and event.get("artifact_id") == artifact_id
    ]
    if not attempts:
        return None
    index, latest = attempts[-1]
    request_id = latest.get("request_id")
    resolved = any(
        event.get("request_id") == request_id
        and event.get("type")
        in {"hackerone_report_submitted", "hackerone_submission_rejected"}
        for event in campaign.events[index + 1 :]
    )
    return None if resolved else latest


@router.get(
    "/api/campaigns/{campaign_id}/reports/{artifact_id}/hackerone-status"
)
def get_hackerone_remote_report_status(
    campaign_id: str,
    artifact_id: str,
):
    from .main import assert_campaign_exists

    campaign = assert_campaign_exists(campaign_id)
    remote = remote_submission_for_artifact(campaign, artifact_id)
    remote_report_id = remote["remote_report_id"]
    try:
        document = HackerOneClient().get_json(
            f"hackers/reports/{remote_report_id}"
        )
    except HackerOneClientError as exc:
        raise _upstream_error(exc) from exc
    return project_remote_report_status(
        document,
        artifact_id=artifact_id,
        expected_report_id=remote_report_id,
        team_handle=remote["team_handle"],
    )


@router.get(
    "/api/campaigns/{campaign_id}/reports/{artifact_id}/hackerone-needs-info-draft"
)
def get_hackerone_needs_more_info_draft(
    campaign_id: str,
    artifact_id: str,
):
    from .main import assert_campaign_exists

    campaign = assert_campaign_exists(campaign_id)
    remote = remote_submission_for_artifact(campaign, artifact_id)
    remote_report_id = remote["remote_report_id"]
    try:
        document = HackerOneClient().get_json(
            f"hackers/reports/{remote_report_id}"
        )
    except HackerOneClientError as exc:
        raise _upstream_error(exc) from exc

    status = project_remote_report_status(
        document,
        artifact_id=artifact_id,
        expected_report_id=remote_report_id,
        team_handle=remote["team_handle"],
    )
    request = status.get("needs_more_info")
    if status.get("state") != "needs-more-info" or not isinstance(request, dict):
        raise HTTPException(
            status_code=409,
            detail="No active public HackerOne needs-more-info request is available",
        )

    return {
        "provider": "hackerone",
        "artifact_id": artifact_id,
        "remote_report_id": remote_report_id,
        "activity_id": request["activity_id"],
        "request": request,
        "draft_markdown": render_needs_more_info_draft(campaign, request),
        "requires_human_review": True,
        "send_supported": False,
    }


@router.post(
    "/api/campaigns/{campaign_id}/reports/{artifact_id}/submit-to-hackerone"
)
def submit_hackerone_report(
    campaign_id: str,
    artifact_id: str,
    payload: HackerOneReportSubmissionInput,
):
    from uuid import uuid4

    from .campaign_audit import append_campaign_event
    from .main import (
        assert_campaign_record,
        assert_campaign_exists,
        save_campaign,
        storage,
        utcnow,
    )
    from .report_approval import approval_status_from_storage
    from .storage import ArtifactIntegrityError
    from .submission_state import submission_event, submission_status

    if not _hackerone_submission_enabled():
        raise HTTPException(
            status_code=409,
            detail="HackerOne external submission is disabled",
        )

    campaign, version = assert_campaign_record(campaign_id)
    store = storage()
    try:
        artifact, report_bytes = store.read_artifact(campaign.id, artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report artifact not found") from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Report artifact integrity verification failed",
        ) from exc
    if artifact.get("kind") != "report":
        raise HTTPException(status_code=409, detail="Artifact is not a report")

    current_state = submission_status(campaign, artifact)
    if current_state.state == "submitted":
        if current_state.platform != "hackerone":
            raise HTTPException(
                status_code=409,
                detail="Report is already marked submitted to another platform",
            )
        remote = latest_remote_submission(campaign, artifact_id)
        result = current_state.to_dict()
        result["remote_report_id"] = remote.get("remote_report_id") if remote else None
        result["team_handle"] = remote.get("team_handle") if remote else None
        return result

    if _unresolved_hackerone_attempt(campaign, artifact_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Previous HackerOne submission attempt is unresolved; reconcile it before retrying",
        )

    try:
        approval = approval_status_from_storage(campaign, store, artifact_id)
    except (KeyError, ValueError, ArtifactIntegrityError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Report approval could not be verified",
        ) from exc
    if not approval.approved or approval.stale:
        raise HTTPException(
            status_code=409,
            detail="HackerOne submission requires current human approval",
        )

    confirmed = [finding for finding in campaign.findings if finding.status == "confirmed"]
    if len(confirmed) != 1:
        raise HTTPException(
            status_code=409,
            detail="HackerOne direct submission requires exactly one confirmed finding",
        )
    finding = confirmed[0]
    if not finding.impact.strip():
        raise HTTPException(
            status_code=409,
            detail="HackerOne direct submission requires reviewed impact text",
        )

    team_handle = _verified_remote_team_handle(campaign)
    try:
        report_text = report_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=409,
            detail="Approved report artifact is not valid UTF-8",
        ) from exc

    severity_rating = "none" if finding.severity == "info" else finding.severity
    outbound = {
        "data": {
            "type": "report",
            "attributes": {
                "team_handle": team_handle,
                "title": finding.title,
                "vulnerability_information": report_text,
                "impact": finding.impact,
                "severity_rating": severity_rating,
            },
        }
    }

    request_id = str(uuid4())
    append_campaign_event(
        campaign.events,
        {
            "type": "hackerone_submission_attempted",
            "artifact_id": artifact_id,
            "artifact_sha256": artifact["sha256"],
            "request_id": request_id,
            "team_handle": team_handle,
            "actor": payload.actor,
            "at": utcnow(),
        },
    )
    campaign.updated_at = utcnow()
    save_campaign(campaign, expected_version=version)

    try:
        response = HackerOneClient().post_json("hackers/reports", outbound)
    except HackerOneClientError as exc:
        if exc.status_code is not None and 400 <= exc.status_code < 500:
            current, current_version = assert_campaign_record(campaign_id)
            append_campaign_event(
                current.events,
                {
                    "type": "hackerone_submission_rejected",
                    "artifact_id": artifact_id,
                    "request_id": request_id,
                    "status_code": exc.status_code,
                    "at": utcnow(),
                },
            )
            current.updated_at = utcnow()
            save_campaign(current, expected_version=current_version)
            status = 422 if exc.status_code == 422 else 502
            raise HTTPException(
                status_code=status,
                detail="HackerOne rejected the approved report submission",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=(
                "HackerOne submission outcome is unresolved; "
                "automatic retry is blocked to prevent duplicate reports"
            ),
        ) from exc

    data = response.get("data")
    remote_report_id = data.get("id") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or data.get("type") != "report"
        or not isinstance(remote_report_id, str)
        or not remote_report_id.strip()
    ):
        raise HTTPException(
            status_code=502,
            detail=(
                "HackerOne submission outcome is unresolved because the success "
                "response was invalid; automatic retry is blocked"
            ),
        )

    current, current_version = assert_campaign_record(campaign_id)
    at = utcnow()
    append_campaign_event(
        current.events,
        {
            "type": "hackerone_report_submitted",
            "artifact_id": artifact_id,
            "artifact_sha256": artifact["sha256"],
            "request_id": request_id,
            "remote_report_id": remote_report_id,
            "team_handle": team_handle,
            "actor": payload.actor,
            "at": at,
        },
    )
    append_campaign_event(
        current.events,
        submission_event(artifact_id, payload.actor, "hackerone", at),
    )
    current.updated_at = at
    save_campaign(current, expected_version=current_version)

    latest = assert_campaign_exists(campaign_id)
    result = submission_status(latest, artifact).to_dict()
    result["remote_report_id"] = remote_report_id
    result["team_handle"] = team_handle
    return result
