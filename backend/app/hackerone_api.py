from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, ValidationError, field_validator, model_validator

from .hackerone_attention import build_hackerone_attention_center
from .hackerone_client import (
    HackerOneClient,
    HackerOneClientError,
    fetch_hackerone_program_snapshot,
    load_hackerone_credentials,
)
from .hackerone_catalog import refresh_hackerone_catalog
from .hackerone_live_readiness import build_hackerone_live_readiness
from .hackerone_intelligence import refresh_hackerone_intelligence
from .local_outcome_intelligence import build_local_outcome_signals
from .hackerone_discovery import build_program_discovery
from .value_efficiency import select_diversified_portfolio
from .simple_portfolio import mark_cached_review_profiles
from .hackerone_needs_info import render_needs_more_info_draft
from .hackerone_review_draft import build_hackerone_review_draft
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
    remember_review_profile: StrictBool = False
    preferred_primary_url: HttpUrl | None = None

    @model_validator(mode="after")
    def remote_binding_must_be_complete(self):
        if (self.remote_handle is None) != (self.remote_snapshot_sha256 is None):
            raise ValueError("remote_handle and remote_snapshot_sha256 must be supplied together")
        if self.remember_review_profile:
            if self.remote_handle is None or self.remote_snapshot_sha256 is None:
                raise ValueError("remembered review profiles require a verified remote binding")
            if self.preferred_primary_url is None:
                raise ValueError("remembered review profiles require a preferred primary URL")
        return self


class HackerOneCampaignTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    primary_url: HttpUrl


class HackerOneCampaignAdmissionInput(HackerOneRulesPreviewInput):
    target: HackerOneCampaignTargetInput


class HackerOneBatchLaunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["sequential", "parallel"] = "sequential"
    campaigns: list[HackerOneCampaignAdmissionInput] = Field(
        min_length=1,
        max_length=20,
    )

    @model_validator(mode="after")
    def campaigns_must_be_remote_bound_and_unique(self):
        handles: list[str] = []
        for campaign in self.campaigns:
            if campaign.remote_handle is None or campaign.remote_snapshot_sha256 is None:
                raise ValueError(
                    "batch campaigns require verified HackerOne remote bindings"
                )
            handles.append(campaign.remote_handle)
        if len(set(handles)) != len(handles):
            raise ValueError("batch campaigns must use unique HackerOne programs")
        return self


class HackerOneReviewedBatchLaunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["sequential", "parallel"] = "sequential"
    handles: list[str] = Field(min_length=1, max_length=20)

    @field_validator("handles")
    @classmethod
    def reviewed_handles_must_be_unique(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for handle in value:
            if not isinstance(handle, str):
                raise ValueError("HackerOne program handle is invalid")
            candidate = handle.strip()
            if (
                not candidate
                or candidate != handle
                or candidate != candidate.lower()
                or len(candidate) > 128
            ):
                raise ValueError("HackerOne program handle is invalid")
            normalized.append(candidate)
        if len(set(normalized)) != len(normalized):
            raise ValueError("reviewed batch handles must be unique")
        return normalized


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


def _remote_program_launch_block_reason(program: dict[str, Any]) -> str | None:
    submission_state = str(program.get("submission_state") or "").strip().lower()
    state = str(program.get("state") or "").strip().lower()
    if submission_state in {"paused", "closed", "disabled"}:
        return "program_submissions_not_open"
    if state in {"closed", "disabled", "archived"}:
        return "program_not_currently_open"
    return None


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


@router.get("/api/hackerone/attention")
def hackerone_attention_center(
    limit: int = Query(default=200, ge=1, le=500),
):
    from .main import storage

    campaigns = storage().list_campaigns(limit=limit)
    return build_hackerone_attention_center(campaigns)


@router.get("/api/hackerone/live-readiness")
def hackerone_live_readiness():
    from .main import dependency_readiness

    return build_hackerone_live_readiness(dependency_readiness())


@router.get("/api/imports/hackerone/connection")
def hackerone_connection():
    try:
        load_hackerone_credentials()
    except HackerOneClientError:
        return {"provider": "hackerone", "configured": False}
    return {"provider": "hackerone", "configured": True}


@router.get("/api/imports/hackerone/programs")
def list_hackerone_programs(
    refresh: bool = Query(default=False),
):
    from .main import storage

    store = storage()
    state = store.get_hackerone_catalog_state()
    if refresh or state is None:
        try:
            state = refresh_hackerone_catalog(store, client=HackerOneClient())
        except HackerOneClientError as exc:
            raise _upstream_error(exc) from exc

    return {
        "provider": "hackerone",
        "programs": list(state.get("programs") or []),
        "catalog": {
            "fingerprint": state.get("fingerprint"),
            "checked_at": state.get("checked_at"),
            "changed_at": state.get("changed_at"),
            "change_sequence": int(state.get("change_sequence") or 0),
            "changes": state.get("changes")
            or {"added": [], "removed": [], "changed": []},
            "background_monitor": bool(state.get("background_monitor", True)),
        },
    }


@router.get("/api/imports/hackerone/catalog")
def hackerone_program_catalog():
    from .main import storage

    state = storage().get_hackerone_catalog_state()
    if state is None:
        try:
            state = refresh_hackerone_catalog(storage(), client=HackerOneClient())
        except HackerOneClientError as exc:
            raise _upstream_error(exc) from exc
    return {
        "provider": "hackerone",
        "read_only": True,
        "contains_secrets": False,
        **state,
    }


@router.get("/api/hackerone/discovery")
def hackerone_program_discovery(
    verify_limit: int = Query(default=20, ge=0, le=50),
):
    """Return a low-friction READY/REVIEW/BLOCKED program selection view."""
    from .main import storage

    store = storage()
    catalog = store.get_hackerone_catalog_state()
    if catalog is None:
        try:
            catalog = refresh_hackerone_catalog(store, client=HackerOneClient())
        except HackerOneClientError as exc:
            raise _upstream_error(exc) from exc

    intelligence = store.get_hackerone_intelligence_state() or {}
    profiles = store.list_hackerone_review_profiles(limit=1000)

    verified: dict[str, str] = {}
    handles = []
    for profile in profiles:
        handle = str(profile.get("handle") or "")
        if handle and handle not in handles:
            handles.append(handle)
        if len(handles) >= verify_limit:
            break

    for handle in handles:
        try:
            snapshot = fetch_hackerone_program_snapshot(handle)
        except HackerOneClientError:
            continue
        verified[handle] = snapshot.snapshot_sha256

    runtime = dict(intelligence.get("runtime_capability_snapshot") or {})
    local_outcomes = build_local_outcome_signals(
        store.list_campaigns(limit=1000)
    )
    result = build_program_discovery(
        programs=list(catalog.get("programs") or []),
        review_profiles=profiles,
        intelligence=intelligence,
        verified_snapshots=verified,
        runtime=runtime,
        catalog_changes=dict(catalog.get("changes") or {}),
        local_outcomes=local_outcomes,
    )
    return {
        "provider": "hackerone",
        "verified_profile_handles": len(verified),
        "verification_limit": verify_limit,
        "catalog_checked_at": catalog.get("checked_at"),
        **result,
    }


@router.get("/api/hackerone/discovery/selection")
def hackerone_discovery_selection(
    limit: int = Query(default=5, ge=1, le=20),
    min_score: int = Query(default=50, ge=0, le=100),
):
    """Return a server-ranked READY bounty portfolio without launching it."""
    discovery = hackerone_program_discovery(verify_limit=50)
    selected = select_diversified_portfolio(
        list(discovery.get("programs") or []),
        limit=limit,
        min_score=min_score,
    )
    return {
        "provider": "hackerone",
        "selection": selected,
        "handles": [str(item.get("handle") or "") for item in selected if item.get("handle")],
        "limit": limit,
        "min_score": min_score,
        "catalog_checked_at": discovery.get("catalog_checked_at"),
        "read_only": True,
        "automatic_launch": False,
        "scope_expansion": False,
        "requires_launch_revalidation": True,
    }


@router.get("/api/hackerone/simple-selection")
def hackerone_simple_selection():
    """Select 2 easy + 2 medium + 2 high-value candidates from local cache.

    Selection itself never requires a live HackerOne request. Programs with a
    saved review profile are marked REVALIDATE and are checked remotely only
    during preflight/launch.
    """
    from .simple_portfolio import select_simple_six
    from .main import storage

    store = storage()
    catalog = store.get_hackerone_catalog_state()
    if catalog is None:
        try:
            catalog = refresh_hackerone_catalog(store, client=HackerOneClient())
        except HackerOneClientError as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "Catalogue HackerOne indisponible et aucun cache local n’existe encore",
                    "reason": "hackerone_catalog_unavailable_no_cache",
                },
            ) from exc

    intelligence = store.get_hackerone_intelligence_state() or {}
    profiles = store.list_hackerone_review_profiles(limit=1000)
    runtime = dict(intelligence.get("runtime_capability_snapshot") or {})
    local_outcomes = build_local_outcome_signals(store.list_campaigns(limit=1000))
    discovery = build_program_discovery(
        programs=list(catalog.get("programs") or []),
        review_profiles=profiles,
        intelligence=intelligence,
        verified_snapshots={},
        runtime=runtime,
        catalog_changes=dict(catalog.get("changes") or {}),
        local_outcomes=local_outcomes,
    )
    candidates = mark_cached_review_profiles(list(discovery.get("programs") or []))
    result = select_simple_six(candidates)
    return {
        "provider": "hackerone",
        **result,
        "catalog_checked_at": catalog.get("checked_at"),
        "catalog_source": "local-cache",
        "selection_requires_live_hackerone": False,
        "read_only": True,
        "automatic_launch": False,
        "requires_launch_revalidation": True,
    }


@router.get("/api/hackerone/journal")
def hackerone_campaign_journal(
    limit: int = Query(default=50, ge=1, le=200),
):
    """Return a durable, read-only operator journal and learning digest."""
    from .github_learning_sync import learning_sync_configuration
    from .main import storage

    store = storage()
    batches = store.list_hackerone_batches(limit=limit)
    entries: list[dict[str, Any]] = []
    for batch in batches:
        members_out: list[dict[str, Any]] = []
        for member in list(batch.get("members") or []):
            campaign_id = str(member.get("campaign_id") or "")
            campaign = store.get_campaign(campaign_id) if campaign_id else None
            findings = list((campaign or {}).get("findings") or [])
            events = list((campaign or {}).get("events") or [])
            event_types: dict[str, int] = {}
            for event in events:
                kind = str(event.get("type") or "unknown")
                event_types[kind] = event_types.get(kind, 0) + 1
            confirmed = [
                item for item in findings
                if str(item.get("status") or "") == "confirmed"
            ]
            members_out.append({
                "handle": str(member.get("handle") or ""),
                "campaign_id": campaign_id,
                "status": str(member.get("status") or ""),
                "reason": member.get("reason"),
                "campaign_state": str((campaign or {}).get("state") or ""),
                "finding_count": len(findings),
                "confirmed_findings": len(confirmed),
                "finding_brief": [
                    {
                        "title": str(item.get("title") or ""),
                        "severity": str(item.get("severity") or ""),
                        "status": str(item.get("status") or ""),
                        "asset": str(item.get("asset") or ""),
                    }
                    for item in findings[:20]
                ],
                "event_count": len(events),
                "event_types": event_types,
                "brief": (
                    f"{len(events)} action(s) journalisée(s), "
                    f"{len(findings)} finding(s), {len(confirmed)} confirmé(s)"
                ),
                "last_events": [
                    {
                        "type": str(item.get("type") or ""),
                        "at": item.get("at"),
                    }
                    for item in events[-12:]
                ],
            })
        entries.append({
            "batch_id": str(batch.get("id") or ""),
            "mode": str(batch.get("mode") or ""),
            "state": str(batch.get("state") or ""),
            "created_at": batch.get("created_at"),
            "updated_at": batch.get("updated_at"),
            "summary": dict(batch.get("summary") or {}),
            "repository_sync": dict(batch.get("learning_repo_sync") or {}),
            "members": members_out,
        })

    digest = {
        "schema": "xbow-learning-journal-v1",
        "generated_from": "confirmed local campaign outcomes",
        "batch_count": len(entries),
        "campaign_count": sum(len(item["members"]) for item in entries),
        "confirmed_findings": sum(
            member["confirmed_findings"]
            for item in entries
            for member in item["members"]
        ),
        "entries": entries,
        "safety": {
            "authorization_source": "reviewed HackerOne program profiles only",
            "historical_awards_authorize_targets": False,
            "automatic_code_mutation": False,
        },
    }
    sync_config = learning_sync_configuration()
    return {
        "provider": "hackerone",
        "journal": entries,
        "learning_digest": digest,
        "local_outcome_learning": True,
        "repository_sync": sync_config,
        "contains_secrets": False,
        "read_only": True,
    }


@router.get("/api/hackerone/intelligence")
def hackerone_learning_intelligence(
    refresh: bool = Query(default=False),
):
    from .main import storage

    store = storage()
    state = store.get_hackerone_intelligence_state()
    if refresh or state is None:
        try:
            state = refresh_hackerone_intelligence(store, client=HackerOneClient())
        except HackerOneClientError as exc:
            raise _upstream_error(exc) from exc
    return {
        **state,
        "read_only": True,
        "advisory_only": True,
        "automatic_tool_enablement": False,
    }


@router.get("/api/imports/hackerone/programs/{handle}/review-draft")
def get_hackerone_program_review_draft(handle: str):
    try:
        snapshot = fetch_hackerone_program_snapshot(handle)
    except HackerOneClientError as exc:
        raise _upstream_error(exc) from exc
    return build_hackerone_review_draft(snapshot)


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
    """Preview exact executable rules and optionally persist a reviewed profile."""

    from .hackerone_scope_import import HackerOneScopeImportError, import_hackerone_structured_scope
    from .main import TargetInput, storage, utcnow

    remote_binding = _verify_remote_binding(payload)
    try:
        preview = import_hackerone_structured_scope(payload.document)
        policy = _policy_from_input(payload.policy)
        rules = preview.to_program_rules(policy=policy)
    except HackerOneScopeImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    policy_snapshot = policy.to_snapshot()
    profile_persisted = False
    profile_persist_reason = None
    if payload.remember_review_profile:
        reason = _conservative_admission_reason(policy)
        if not preview.complete:
            profile_persist_reason = "scope_review_incomplete"
        elif reason is not None:
            profile_persist_reason = reason
        else:
            try:
                target = TargetInput(
                    name=f"H1 {payload.remote_handle}",
                    primary_url=payload.preferred_primary_url,
                    rules=rules,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            now = utcnow()
            profile = {
                "id": f"{payload.remote_handle}@{payload.remote_snapshot_sha256}",
                "provider": "hackerone",
                "handle": payload.remote_handle,
                "snapshot_sha256": payload.remote_snapshot_sha256,
                "preferred_primary_url": str(target.primary_url),
                "policy": policy_snapshot,
                "policy_snapshot_sha256": _json_sha256(policy_snapshot),
                "saved_at": now,
                "updated_at": now,
                "contains_secrets": False,
            }
            storage().save_hackerone_review_profile(profile)
            profile_persisted = True

    result = {
        "provider": "hackerone",
        "complete": preview.complete,
        "requires_review": True,
        "persisted": False,
        "campaign_created": False,
        "review_profile_persisted": profile_persisted,
        "review_profile_persist_reason": profile_persist_reason,
        "policy_snapshot": policy_snapshot,
        "rules": rules.model_dump(mode="json"),
    }
    if remote_binding is not None:
        result["remote_binding"] = remote_binding
    return result


@router.get("/api/imports/hackerone/review-profiles")
def list_hackerone_review_profiles(
    limit: int = Query(default=500, ge=1, le=1000),
):
    from .main import storage

    return {
        "provider": "hackerone",
        "profiles": storage().list_hackerone_review_profiles(limit=limit),
        "read_only": True,
        "contains_secrets": False,
    }


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


def _batch_summary(members: list[dict[str, Any]]) -> dict[str, int]:
    statuses = ("ready", "running", "done", "review", "blocked", "cancelled")
    return {
        status: sum(
            1
            for member in members
            if str(member.get("status") or "ready") == status
        )
        for status in statuses
    }


def _rollback_admitted_batch_campaigns(campaign_ids: list[str]) -> None:
    from .main import cancel_campaign

    for campaign_id in campaign_ids:
        try:
            cancel_campaign(campaign_id)
        except Exception:
            continue


def _reviewed_campaign_input(
    handle: str,
    store,
) -> HackerOneCampaignAdmissionInput:
    try:
        snapshot = fetch_hackerone_program_snapshot(handle)
    except HackerOneClientError as exc:
        raise _upstream_error(exc) from exc

    block_reason = _remote_program_launch_block_reason(dict(snapshot.program or {}))
    if block_reason is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne program is no longer launchable",
                "reason": block_reason,
                "handles": [snapshot.handle],
            },
        )

    profile_id = f"{snapshot.handle}@{snapshot.snapshot_sha256}"
    profile = store.get_hackerone_review_profile(profile_id)
    if profile is None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne reviewed profile required",
                "reason": "review_profile_required",
                "handles": [snapshot.handle],
            },
        )

    if (
        str(profile.get("handle") or "") != snapshot.handle
        or str(profile.get("snapshot_sha256") or "") != snapshot.snapshot_sha256
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne reviewed profile binding mismatch",
                "reason": "review_profile_binding_mismatch",
                "handles": [snapshot.handle],
            },
        )

    policy_raw = profile.get("policy")
    primary_url = str(profile.get("preferred_primary_url") or "").strip()
    if not isinstance(policy_raw, dict) or not primary_url:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne reviewed profile is incomplete",
                "reason": "review_profile_incomplete",
                "handles": [snapshot.handle],
            },
        )

    try:
        policy = HackerOneProgramPolicyInput.model_validate(policy_raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne reviewed profile policy is invalid",
                "reason": "review_profile_invalid",
                "handles": [snapshot.handle],
            },
        ) from exc

    program_name = str(snapshot.program.get("name") or "").strip()
    if len(program_name) < 2:
        program_name = f"H1 {snapshot.handle}"
    program_name = program_name[:120]

    try:
        return HackerOneCampaignAdmissionInput(
            document=snapshot.document,
            policy=policy,
            target=HackerOneCampaignTargetInput(
                name=program_name,
                primary_url=primary_url,
            ),
            remote_handle=snapshot.handle,
            remote_snapshot_sha256=snapshot.snapshot_sha256,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne reviewed profile target is invalid",
                "reason": "review_profile_invalid",
                "handles": [snapshot.handle],
            },
        ) from exc


@router.post("/api/imports/hackerone/batches/go-no-go")
def hackerone_batch_go_no_go(payload: HackerOneReviewedBatchLaunchInput):
    """Return one read-only prelaunch verdict without creating campaigns."""
    from .main import dependency_readiness

    runtime = build_hackerone_live_readiness(dependency_readiness())
    batch = preflight_reviewed_hackerone_batch(payload)
    runtime_ready = runtime.get("live_scan_ready") is True
    batch_ready = batch.get("ready") is True
    blockers = []
    if not runtime_ready:
        blockers.extend(
            str(item.get("id") or "runtime_check")
            for item in list(runtime.get("checks") or [])
            if isinstance(item, dict)
            and item.get("required") is True
            and item.get("ok") is not True
        )
    blockers.extend(
        str(item.get("handle") or "program")
        + ":"
        + str(item.get("reason") or "blocked")
        for item in list(batch.get("members") or [])
        if isinstance(item, dict) and item.get("status") == "blocked"
    )
    return {
        "provider": "hackerone",
        "go": bool(runtime_ready and batch_ready),
        "runtime_ready": runtime_ready,
        "batch_ready": batch_ready,
        "blockers": blockers,
        "runtime": runtime,
        "batch": batch,
        "read_only": True,
        "campaigns_created": False,
        "automatic_launch": False,
        "scope_expansion": False,
    }


@router.post("/api/imports/hackerone/batches/preflight-reviewed")
def preflight_reviewed_hackerone_batch(payload: HackerOneReviewedBatchLaunchInput):
    """Validate every selected reviewed program without creating campaigns."""
    from .main import storage

    store = storage()
    members: list[dict[str, Any]] = []
    for handle in payload.handles:
        try:
            prepared = _reviewed_campaign_input(handle, store)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            members.append({
                "handle": handle,
                "status": "blocked",
                "reason": str(detail.get("reason") or "reviewed_preflight_blocked"),
                "message": str(detail.get("message") or exc.detail),
            })
            continue
        members.append({
            "handle": handle,
            "status": "ready",
            "snapshot_sha256": str(prepared.remote_snapshot_sha256 or ""),
        })

    ready = [item for item in members if item["status"] == "ready"]
    blocked = [item for item in members if item["status"] == "blocked"]
    return {
        "provider": "hackerone",
        "mode": payload.mode,
        "ready": len(blocked) == 0 and len(ready) == len(members),
        "members": members,
        "summary": {
            "total": len(members),
            "ready": len(ready),
            "blocked": len(blocked),
        },
        "read_only": True,
        "campaigns_created": False,
        "automatic_launch": False,
        "scope_expansion": False,
        "requires_launch_revalidation": True,
    }


@router.post("/api/imports/hackerone/batches/launch-reviewed")
def launch_reviewed_hackerone_batch(payload: HackerOneReviewedBatchLaunchInput):
    from .main import storage

    store = storage()
    prepared: list[HackerOneCampaignAdmissionInput] = []
    missing: list[str] = []

    for handle in payload.handles:
        try:
            prepared.append(_reviewed_campaign_input(handle, store))
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            if exc.status_code == 409 and detail.get("reason") == "review_profile_required":
                missing.extend(
                    str(item)
                    for item in detail.get("handles", [])
                    if str(item)
                )
                continue
            raise

    if missing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne reviewed profile required",
                "reason": "review_profile_required",
                "handles": sorted(set(missing)),
            },
        )

    verdict = hackerone_batch_go_no_go(payload)
    if verdict.get("go") is not True:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "HackerOne reviewed batch go/no-go blocked",
                "reason": "batch_go_no_go_blocked",
                "blockers": list(verdict.get("blockers") or []),
            },
        )

    return launch_hackerone_batch(
        HackerOneBatchLaunchInput(
            mode=payload.mode,
            campaigns=prepared,
        )
    )


@router.post("/api/imports/hackerone/batches/launch")
def launch_hackerone_batch(payload: HackerOneBatchLaunchInput):
    from .campaign_audit import append_campaign_event
    from .hackerone_batch import reconcile_hackerone_batch
    from .main import (
        assert_campaign_record,
        save_campaign,
        storage,
        queue,
        utcnow,
    )

    batch_id = str(uuid4())
    admitted_ids: list[str] = []
    members: list[dict[str, Any]] = []

    try:
        for index, campaign_payload in enumerate(payload.campaigns):
            admitted = admit_hackerone_campaign(campaign_payload)
            campaign_id = str(admitted["campaign"]["id"])
            admitted_ids.append(campaign_id)
            members.append(
                {
                    "index": index,
                    "campaign_id": campaign_id,
                    "handle": str(campaign_payload.remote_handle),
                    "snapshot_sha256": str(
                        campaign_payload.remote_snapshot_sha256
                    ),
                    "status": "ready",
                    "reason": None,
                }
            )

        for member in members:
            campaign, version = assert_campaign_record(member["campaign_id"])
            append_campaign_event(
                campaign.events,
                {
                    "type": "hackerone_batch_member",
                    "batch_id": batch_id,
                    "batch_mode": payload.mode,
                    "batch_index": member["index"],
                    "at": utcnow(),
                },
            )
            campaign.updated_at = utcnow()
            save_campaign(campaign, expected_version=version)

        now = utcnow()
        batch = {
            "id": batch_id,
            "provider": "hackerone",
            "mode": payload.mode,
            "state": "queued",
            "members": members,
            "summary": _batch_summary(members),
            "created_at": now,
            "updated_at": now,
            "continues_without_dashboard": True,
            "automatic_submission": False,
        }
        store = storage()
        store.save_hackerone_batch(batch, expected_version=0)
    except Exception:
        _rollback_admitted_batch_campaigns(admitted_ids)
        raise

    reconcile_hackerone_batch(queue(), storage(), batch_id)

    latest = storage().get_hackerone_batch(batch_id)
    if latest is None:
        raise HTTPException(status_code=500, detail="HackerOne batch disappeared")
    return latest


@router.get("/api/imports/hackerone/batches")
def list_hackerone_batches(
    limit: int = Query(default=50, ge=1, le=200),
):
    from .main import storage

    return {
        "provider": "hackerone",
        "batches": storage().list_hackerone_batches(limit=limit),
        "read_only": True,
    }


@router.get("/api/imports/hackerone/batches/{batch_id}")
def get_hackerone_batch(batch_id: str):
    from .hackerone_batch import reconcile_hackerone_batch
    from .main import queue, storage

    batch = reconcile_hackerone_batch(queue(), storage(), batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="HackerOne batch not found")
    return batch


@router.post("/api/imports/hackerone/batches/{batch_id}/cancel")
def cancel_hackerone_batch(batch_id: str):
    from .main import cancel_campaign, storage, utcnow

    store = storage()
    record = store.get_hackerone_batch_record(batch_id)
    if record is None:
        raise HTTPException(status_code=404, detail="HackerOne batch not found")
    batch, version = record
    if str(batch.get("state")) == "cancelled":
        return batch

    for member in batch.get("members", []):
        if str(member.get("status")) in {"done", "cancelled"}:
            continue
        try:
            cancel_campaign(str(member["campaign_id"]))
        except HTTPException as exc:
            member["reason"] = str(exc.detail)[:500]
        except Exception as exc:
            member["reason"] = exc.__class__.__name__
        member["status"] = "cancelled"

    batch["state"] = "cancelled"
    batch["summary"] = _batch_summary(batch.get("members", []))
    batch["updated_at"] = utcnow()
    store.save_hackerone_batch(batch, expected_version=version)
    return batch


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
