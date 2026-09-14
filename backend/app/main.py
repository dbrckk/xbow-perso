from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from fnmatch import fnmatch
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, HttpUrl, model_validator

from .api_outbox import has_event, outbox_snapshot, pending_request_id
from .api_rate_limit import api_rate_limit_middleware
from .auth import AuthError, require_api_token
from .campaign_audit import append_campaign_event, verify_campaign_event_chain
from .job_provenance import attach_job_provenance, verify_job_provenance
from .policy_integrity import seal_policy_receipt, verify_policy_receipt
from .queue_backend import QueueBackend, create_queue
from .readiness import readiness as dependency_readiness
from .storage import ArtifactIntegrityError, CampaignConflictError
from .storage_backend import StorageBackend, create_storage
from .totp_auth import require_totp_for_mutation
from .validation_state import has_evidence_backed_independent_validation

app = FastAPI(title="xbow-perso", version="0.4.0")


@app.middleware("http")
async def authenticate_control_api(request: Request, call_next):
    if request.url.path.startswith("/api/") or request.url.path == "/api":
        try:
            require_api_token(request)
            require_totp_for_mutation(request)
        except AuthError as exc:
            headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)
    return await call_next(request)


app.middleware("http")(api_rate_limit_middleware)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def storage() -> StorageBackend:
    return create_storage()


def queue() -> QueueBackend:
    return create_queue()


def _stable_key(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


class CampaignState(str, Enum):
    draft = "draft"
    ready = "ready"
    running = "running"
    validating = "validating"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class ProgramRules(BaseModel):
    authorization_reference: str = Field(min_length=3)
    allowed_targets: list[str] = Field(min_length=1)
    denied_targets: list[str] = Field(default_factory=list)
    max_requests_per_second: float = Field(default=2.0, gt=0, le=20)
    destructive_testing: bool = False
    denial_of_service: bool = False
    social_engineering: bool = False
    credential_attacks: bool = False
    automated_scanning: bool = True
    notes: str = ""


class TargetInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    primary_url: HttpUrl
    rules: ProgramRules
    credentials_note: str | None = None

    @model_validator(mode="after")
    def primary_target_must_be_allowed(self):
        parsed = urlparse(str(self.primary_url))
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("primary_url has no hostname")
        if parsed.username or parsed.password:
            raise ValueError("userinfo in primary_url is forbidden")
        if parsed.query or parsed.fragment:
            raise ValueError("query strings and fragments in primary_url are forbidden")
        if not is_host_allowed(host, self.rules.allowed_targets, self.rules.denied_targets):
            raise ValueError("primary_url is outside the declared scope")
        return self


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    asset: str
    endpoint: str | None = None
    summary: str
    evidence: list[str] = Field(default_factory=list)
    reproduction_steps: list[str] = Field(default_factory=list)
    impact: str = ""
    remediation: str = ""
    cwe: str | None = None
    cvss: float | None = Field(default=None, ge=0, le=10)
    status: Literal["candidate", "validation_required", "confirmed", "rejected"] = "candidate"
    discovered_by: str = "unknown"
    validated_by: str | None = None


class Campaign(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    target: TargetInput
    state: CampaignState = CampaignState.draft
    created_at: str = Field(default_factory=utcnow)
    updated_at: str = Field(default_factory=utcnow)
    findings: list[Finding] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceInput(BaseModel):
    kind: Literal["scanner_stdout", "scanner_stderr", "http_evidence", "validation", "report"]
    content: str = Field(max_length=1_000_000)
    media_type: str = Field(default="text/plain", max_length=120)
    finding_id: str | None = None


class HackerOneScopePreviewInput(BaseModel):
    document: dict[str, Any]


def normalize_pattern(pattern: str) -> str:
    value = pattern.strip().lower()
    if "://" in value:
        value = (urlparse(value).hostname or value).lower()
    return value.rstrip(".")


def is_host_allowed(host: str, allowed: list[str], denied: list[str]) -> bool:
    host = host.lower().rstrip(".")
    denied_patterns = [normalize_pattern(x) for x in denied]
    if any(fnmatch(host, p) for p in denied_patterns):
        return False
    allowed_patterns = [normalize_pattern(x) for x in allowed]
    return any(fnmatch(host, p) for p in allowed_patterns)


def save_campaign(campaign: Campaign, *, expected_version: int | None = None) -> int:
    try:
        return storage().save_campaign(campaign.model_dump(mode="json"), expected_version=expected_version)
    except CampaignConflictError as exc:
        raise HTTPException(status_code=409, detail="Campaign changed concurrently; reload and retry") from exc


def assert_campaign_record(campaign_id: str) -> tuple[Campaign, int]:
    record = storage().get_campaign_record(campaign_id)
    if not record:
        raise HTTPException(status_code=404, detail="Campaign not found")
    document, version = record
    return Campaign.model_validate(document), version


def assert_campaign_exists(campaign_id: str) -> Campaign:
    return assert_campaign_record(campaign_id)[0]


def _reject_cancelled_campaign(campaign: Campaign) -> None:
    if campaign.state == CampaignState.cancelled:
        raise HTTPException(status_code=409, detail="Campaign is cancelled")


def _reject_new_findings_for_closed_campaign(campaign: Campaign) -> None:
    if campaign.state in {CampaignState.cancelled, CampaignState.completed}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot add findings to {campaign.state.value} campaign",
        )


def _campaign_graph(campaign_id: str):
    from .observation_graph import ObservationGraph

    assert_campaign_exists(campaign_id)
    return ObservationGraph.from_records(storage().list_observations(campaign_id))


def _has_evidence_backed_independent_validation(campaign_id: str, finding: Finding) -> bool:
    graph = _campaign_graph(campaign_id)
    return has_evidence_backed_independent_validation(graph, f"finding:{finding.id}")


def policy_receipt(campaign: Campaign, host: str, action: str) -> dict[str, Any]:
    rules = campaign.target.rules
    allowed = is_host_allowed(host, rules.allowed_targets, rules.denied_targets)
    blocked_actions = {
        "destructive": rules.destructive_testing is False,
        "dos": rules.denial_of_service is False,
        "social_engineering": rules.social_engineering is False,
        "credential_attack": rules.credential_attacks is False,
        "automated_scan": rules.automated_scanning is False,
    }
    action_known = action in blocked_actions
    action_blocked = blocked_actions.get(action, True)
    return seal_policy_receipt(
        {
            "allowed": allowed and not action_blocked,
            "host": host,
            "action": action,
            "action_known": action_known,
            "scope_allowed": allowed,
            "action_blocked": action_blocked,
            "authorization_reference": rules.authorization_reference,
            "timestamp": utcnow(),
        }
    )


def sanitized_scan_payload(
    campaign: Campaign,
    receipt: dict[str, Any],
    *,
    job_kind: str = "strix_scan",
) -> dict[str, Any]:
    """Return deterministic worker input suitable for queue idempotency.

    The audit receipt keeps its timestamp in campaign events/API responses, but
    transient timestamps must never enter a deduplicated queue payload.
    """
    transient = {"timestamp", "receipt_hash", "signature", "signature_alg", "integrity_mode"}
    stable_receipt = {key: value for key, value in receipt.items() if key not in transient}
    payload = {
        "campaign_id": campaign.id,
        "target": str(campaign.target.primary_url),
        "policy": stable_receipt,
        "rules": {
            "allowed_targets": campaign.target.rules.allowed_targets,
            "denied_targets": campaign.target.rules.denied_targets,
            "max_requests_per_second": campaign.target.rules.max_requests_per_second,
            "destructive_testing": False,
            "denial_of_service": False,
            "social_engineering": False,
            "credential_attacks": False,
            "automated_scanning": campaign.target.rules.automated_scanning,
        },
    }
    return attach_job_provenance(
        payload,
        campaign,
        job_kind=job_kind,
        action="automated_scan",
    )


@app.get("/live")
def live():
    return {"ok": True, "service": "xbow-perso", "version": app.version}


@app.get("/ready")
def ready():
    dependencies = dependency_readiness()
    payload = {
        "ok": bool(dependencies.get("ok")),
        "service": "xbow-perso",
        "version": app.version,
    }
    if not payload["ok"]:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/health")
def health():
    try:
        database_ok = bool(queue().health().get("ok"))
    except Exception:
        database_ok = False
    payload = {
        "ok": database_ok,
        "service": "xbow-perso",
        "version": app.version,
    }
    if not payload["ok"]:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/api/deployment/preflight")
def deployment_preflight():
    from .deployment_preflight import build_deployment_preflight

    return build_deployment_preflight(dependency_readiness())


@app.get("/api/capabilities")
def system_capabilities():
    from .runtime_capabilities import (
        safe_pentagi_runtime_capability,
        safe_scanner_runtime_capability,
    )

    pentagi = safe_pentagi_runtime_capability()
    scanners = safe_scanner_runtime_capability()
    return {
        "campaign_control": {
            "scope_enforcement": True,
            "durable_queue": True,
            "artifact_integrity": "sha256",
            "optimistic_campaign_versioning": True,
            "crash_safe_outbox": True,
            "outbox_observability": True,
            "policy_bound_job_provenance": True,
            "queue_transition_audit": True,
            "queue_recovery_assessment": True,
            "signed_recovery_attestation": True,
            "recovery_readiness_gate": True,
            "operations_dashboard": True,
            "control_plane_health_model": True,
            "control_plane_health_history": True,
            "slo_error_budgets": True,
        },
        "execution": {
            "strix_scanning": "gated",
            "scanner_worker": scanners["mode"],
            "scanner_worker_detail": scanners,
            "http_validation": "gated",
            "browser_automation": "gated",
            "pentagi": pentagi["mode"],
            "pentagi_detail": pentagi,
            "pentagi_status_tracking": (
                "available"
                if pentagi["status_tracking"]["available"]
                else "disabled"
            ),
            "default_mode": "dry_run" if pentagi["dry_run"] else "active",
            "arbitrary_shell_jobs": False,
        },
        "reasoning": {
            "adaptive_planning": "advisory",
            "observation_graph": True,
            "knowledge_memory": True,
            "hypothesis_engine": "read_only",
            "finding_triage": "read_only",
            "evidence_quality_scoring": "read_only",
            "review_queue": "read_only",
            "decision_consensus": "read_only",
        },
        "reporting": {
            "report_generation": True,
            "human_approval_required": True,
            "submission_state_tracking": True,
            "external_platform_submission": False,
        },
        "safety": {
            "destructive_testing": False,
            "denial_of_service": False,
            "social_engineering": False,
            "credential_attacks": False,
            "exploit_execution": False,
            "out_of_scope_execution": False,
            "pentagi_remote_execution_enforceable": bool(
                pentagi["execution_transport_enforceable"]
            ),
            "scanner_sandbox_admission_enforced": bool(
                scanners["worker_admission_enforced"]
            ),
        },
    }


@app.get("/api/agents")
def list_agents():
    from .agent_registry import public_agent_catalog
    return public_agent_catalog()


@app.post("/api/imports/hackerone/scope-preview")
def preview_hackerone_scope(payload: HackerOneScopePreviewInput):
    from .hackerone_scope_import import (
        HackerOneScopeImportError,
        import_hackerone_structured_scope,
    )

    try:
        preview = import_hackerone_structured_scope(payload.document)
    except HackerOneScopeImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "provider": "hackerone",
        "complete": preview.complete,
        "requires_review": True,
        "persisted": False,
        "campaign_created": False,
        "allowed_targets": list(preview.allowed_targets),
        "denied_targets": list(preview.denied_targets),
        "conflicts": list(preview.conflicts),
        "unsupported": list(preview.unsupported),
        "assets": [
            {
                "identifier": asset.identifier,
                "asset_type": asset.asset_type,
                "eligible_for_submission": asset.eligible_for_submission,
                "host_pattern": asset.host_pattern,
                "compatible": asset.compatible,
                "reason": asset.reason,
            }
            for asset in preview.assets
        ],
    }


@app.post("/api/campaigns", response_model=Campaign)
def create_campaign(target: TargetInput):
    campaign = Campaign(target=target, state=CampaignState.ready)
    append_campaign_event(campaign.events, {"type": "campaign_created", "at": utcnow()})
    save_campaign(campaign, expected_version=0)
    return campaign


@app.get("/api/campaigns", response_model=list[Campaign])
def list_campaigns():
    return [Campaign.model_validate(x) for x in storage().list_campaigns()]


@app.get("/api/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str):
    return assert_campaign_exists(campaign_id)


@app.get("/api/campaigns/{campaign_id}/outbox")
def campaign_outbox_status(campaign_id: str, limit: int = 100):
    campaign = assert_campaign_exists(campaign_id)
    try:
        snapshot = outbox_snapshot(campaign.events, max_items=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "campaign_id": campaign.id,
        **snapshot,
        "read_only": True,
    }


@app.get("/api/campaigns/{campaign_id}/outbox/recovery")
def campaign_outbox_recovery(campaign_id: str):
    from .outbox_recovery import (
        diagnose_outbox_recovery,
        public_recovery_diagnostics,
    )

    campaign = assert_campaign_exists(campaign_id)
    diagnostics = diagnose_outbox_recovery(
        campaign.id,
        campaign.events,
        queue(),
    )
    return {
        "campaign_id": campaign.id,
        "diagnostics": public_recovery_diagnostics(diagnostics),
        "read_only": True,
        "local_repair_only": True,
        "automatic_job_creation": False,
    }


def _apply_local_outbox_repairs(
    campaign: Campaign,
    diagnostics: list[dict[str, Any]],
) -> tuple[int, int]:
    from .outbox_recovery import local_completion_event

    repaired = 0
    skipped_ambiguous = 0

    for diagnostic in diagnostics:
        intent = diagnostic.get("_intent") or {}
        job = diagnostic.get("_job") or {}
        if intent.get("kind") == "campaign_start":
            job_status = str(job.get("status") or "")
            if campaign.state in {
                CampaignState.running,
                CampaignState.validating,
                CampaignState.completed,
            }:
                pass
            elif (
                campaign.state in {CampaignState.ready, CampaignState.failed}
                and job_status in {"queued", "running"}
            ):
                campaign.state = CampaignState.running
            else:
                skipped_ambiguous += 1
                continue

        event = local_completion_event(diagnostic, at=utcnow())
        if event is None:
            continue
        append_campaign_event(campaign.events, event)
        repaired += 1

    return repaired, skipped_ambiguous


@app.post("/api/campaigns/{campaign_id}/outbox/reconcile-local")
def reconcile_campaign_outbox_local(campaign_id: str):
    from .outbox_recovery import (
        diagnose_outbox_recovery,
        public_recovery_diagnostics,
    )

    jobs = queue()
    last_conflict: HTTPException | None = None

    for _ in range(3):
        campaign, version = assert_campaign_record(campaign_id)
        _reject_cancelled_campaign(campaign)
        diagnostics = diagnose_outbox_recovery(
            campaign.id,
            campaign.events,
            jobs,
        )
        repaired, skipped_ambiguous = _apply_local_outbox_repairs(
            campaign,
            diagnostics,
        )

        if repaired:
            campaign.updated_at = utcnow()
            try:
                save_campaign(campaign, expected_version=version)
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                last_conflict = exc
                continue

        latest = assert_campaign_exists(campaign.id)
        remaining = diagnose_outbox_recovery(
            latest.id,
            latest.events,
            jobs,
        )
        return {
            "campaign_id": latest.id,
            "repaired": repaired,
            "skipped_ambiguous": skipped_ambiguous,
            "remaining": public_recovery_diagnostics(remaining),
            "local_repair_only": True,
            "automatic_job_creation": False,
        }

    raise HTTPException(
        status_code=409,
        detail=(
            "Outbox reconciliation conflicted repeatedly; reload and retry"
            if last_conflict is not None
            else "Outbox reconciliation did not converge"
        ),
    )


@app.get("/api/campaigns/{campaign_id}/pentagi/preview")
def preview_pentagi_campaign(campaign_id: str):
    from .pentagi_adapter import PentagiPolicyError
    from .pentagi_admission import PentagiAdmissionError
    from .pentagi_control import PentagiControlError, prepare_pentagi_control_preview

    campaign = assert_campaign_exists(campaign_id)
    _reject_cancelled_campaign(campaign)
    try:
        preview = prepare_pentagi_control_preview(campaign)
    except (PentagiPolicyError, PentagiAdmissionError, PentagiControlError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "campaign_id": campaign.id,
        "ready": preview.ready,
        "admission": {
            "allowed": preview.decision.allowed,
            "reasons": list(preview.decision.reasons),
            "policy_fingerprint": preview.decision.policy_fingerprint,
            "max_requests_per_second": preview.decision.max_requests_per_second,
        },
        "operational_reasons": list(preview.operational_reasons),
        "plan": {
            "target": preview.plan.target,
            "model_provider": preview.plan.model_provider,
            "execution_supported": preview.plan.execution_supported,
        },
        "request_payload_exposed": False,
    }


def _pentagi_dispatch_fingerprint(idempotency_key: str) -> str:
    return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


def _record_pentagi_dispatch_intent(
    campaign: Campaign,
    version: int,
    *,
    dispatch_fingerprint: str,
    policy_fingerprint: str,
) -> int:
    if any(
        event.get("type") == "pentagi_dispatch_requested"
        and event.get("dispatch_fingerprint") == dispatch_fingerprint
        for event in campaign.events
    ):
        return version
    append_campaign_event(
        campaign.events,
        {
            "type": "pentagi_dispatch_requested",
            "at": utcnow(),
            "dispatch_fingerprint": dispatch_fingerprint,
            "policy_fingerprint": policy_fingerprint,
        },
    )
    campaign.updated_at = utcnow()
    return save_campaign(campaign, expected_version=version)


def _reconcile_pentagi_queued_event(
    campaign_id: str,
    job: dict[str, Any],
    *,
    dispatch_fingerprint: str,
    policy_fingerprint: str,
    attempts: int = 3,
) -> Campaign:
    for _ in range(attempts):
        campaign, version = assert_campaign_record(campaign_id)
        if any(
            event.get("type") == "pentagi_flow_queued"
            and event.get("job_id") == job["id"]
            for event in campaign.events
        ):
            return campaign
        if campaign.state == CampaignState.cancelled:
            raise HTTPException(
                status_code=409,
                detail="Campaign was cancelled while PentAGI dispatch was being reconciled",
            )
        append_campaign_event(
            campaign.events,
            {
                "type": "pentagi_flow_queued",
                "at": utcnow(),
                "job_id": job["id"],
                "dispatch_fingerprint": dispatch_fingerprint,
                "policy_fingerprint": policy_fingerprint,
            },
        )
        if campaign.state in {CampaignState.ready, CampaignState.failed}:
            campaign.state = CampaignState.running
        campaign.updated_at = utcnow()
        try:
            save_campaign(campaign, expected_version=version)
            return campaign
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
    raise HTTPException(
        status_code=409,
        detail="PentAGI job queued but campaign audit reconciliation conflicted; retry safely",
    )


@app.post("/api/campaigns/{campaign_id}/pentagi/dispatch")
def dispatch_pentagi_campaign(campaign_id: str):
    from .pentagi_adapter import PentagiPolicyError
    from .pentagi_admission import PentagiAdmissionError
    from .pentagi_control import PentagiControlError, require_pentagi_control_ready
    from .pentagi_dispatch import (
        enqueue_pentagi_flow,
        prepare_pentagi_execution_permit,
    )
    from .pentagi_execution_guard import PentagiExecutionGuardError

    campaign, version = assert_campaign_record(campaign_id)
    _reject_cancelled_campaign(campaign)
    if campaign.state not in {
        CampaignState.ready,
        CampaignState.running,
        CampaignState.failed,
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot dispatch PentAGI from {campaign.state.value}",
        )
    try:
        preview = require_pentagi_control_ready(campaign)
        permit = prepare_pentagi_execution_permit(campaign, preview.plan)
        dispatch_fingerprint = _pentagi_dispatch_fingerprint(permit.idempotency_key)
        _record_pentagi_dispatch_intent(
            campaign,
            version,
            dispatch_fingerprint=dispatch_fingerprint,
            policy_fingerprint=preview.decision.policy_fingerprint,
        )
        job = enqueue_pentagi_flow(
            queue(),
            campaign,
            preview.plan,
            permit=permit,
        )
    except (
        PentagiPolicyError,
        PentagiAdmissionError,
        PentagiControlError,
        PentagiExecutionGuardError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    campaign = _reconcile_pentagi_queued_event(
        campaign.id,
        job,
        dispatch_fingerprint=dispatch_fingerprint,
        policy_fingerprint=preview.decision.policy_fingerprint,
    )
    safe_job = {
        key: job.get(key)
        for key in (
            "id",
            "kind",
            "status",
            "attempts",
            "max_attempts",
            "created_at",
            "updated_at",
        )
    }
    return {
        "campaign_id": campaign.id,
        "job": safe_job,
        "policy_fingerprint": preview.decision.policy_fingerprint,
        "audit_reconciled": True,
    }


@app.get("/api/campaigns/{campaign_id}/pentagi")
def pentagi_campaign_status(campaign_id: str):
    campaign = assert_campaign_exists(campaign_id)
    counts = queue().campaign_job_counts(campaign.id)
    artifacts = [
        {
            key: item.get(key)
            for key in (
                "id",
                "kind",
                "media_type",
                "sha256",
                "size_bytes",
                "created_at",
            )
        }
        for item in storage().list_artifacts(campaign.id)
        if item.get("kind") in {"pentagi_receipt", "pentagi_status"}
    ]
    return {
        "campaign_id": campaign.id,
        "jobs": {
            "pentagi_flow": counts.get("pentagi_flow", 0),
            "pentagi_status": counts.get("pentagi_status", 0),
        },
        "artifacts": artifacts,
        "read_only": True,
    }


@app.get("/api/campaigns/{campaign_id}/observations")
def list_campaign_observations(campaign_id: str):
    assert_campaign_exists(campaign_id)
    return storage().list_observations(campaign_id)


@app.get("/api/campaigns/{campaign_id}/audit/decisions")
def campaign_decision_audit(campaign_id: str):
    from .decision_audit import verify_decision_audit_chain

    graph = _campaign_graph(campaign_id)
    return {
        "campaign_id": campaign_id,
        **verify_decision_audit_chain(graph),
        "read_only": True,
    }


@app.get("/api/campaigns/{campaign_id}/audit/events")
def campaign_event_audit(campaign_id: str):
    campaign = assert_campaign_exists(campaign_id)
    return {
        "campaign_id": campaign_id,
        **verify_campaign_event_chain(campaign.events),
        "read_only": True,
    }


@app.get("/api/campaigns/{campaign_id}/audit/queue-transitions")
def campaign_queue_transition_audit(campaign_id: str):
    campaign = assert_campaign_exists(campaign_id)
    return {
        **queue().campaign_transition_audit(campaign.id),
        "read_only": True,
        "payload_exposed": False,
        "errors_exposed": False,
        "worker_identity_exposed": False,
    }


@app.get("/api/campaigns/{campaign_id}/audit/workers")
def campaign_worker_audit(campaign_id: str):
    from .worker_audit import verify_worker_audit_chain

    campaign = assert_campaign_exists(campaign_id)
    return {
        "campaign_id": campaign_id,
        **verify_worker_audit_chain(campaign.events),
        "read_only": True,
    }


@app.get("/api/campaigns/{campaign_id}/knowledge")
def campaign_knowledge(campaign_id: str):
    from .knowledge_memory import build_knowledge_snapshot, decision_history, rank_findings
    campaign = assert_campaign_exists(campaign_id)
    graph = _campaign_graph(campaign_id)
    from .hypothesis_memory import build_hypotheses

    return {
        "snapshot": build_knowledge_snapshot(graph).to_dict(),
        "priorities": [item.to_dict() for item in rank_findings(campaign.findings, graph)],
        "hypotheses": [item.to_dict() for item in build_hypotheses(graph)],
        "decision_history": decision_history(graph),
    }


@app.get("/api/campaigns/{campaign_id}/findings/ranking")
def campaign_finding_ranking(campaign_id: str, history_limit: int = 50):
    from .hypothesis_memory import summarize_hypothesis_stability
    from .knowledge_memory import rank_findings_explainable

    campaign = assert_campaign_exists(campaign_id)
    graph = _campaign_graph(campaign_id)
    try:
        snapshots = storage().list_hypothesis_snapshots(campaign_id, limit=history_limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stability = {
        item["finding_id"]: item
        for item in summarize_hypothesis_stability(snapshots)
    }
    return {
        "campaign_id": campaign.id,
        "findings": rank_findings_explainable(
            campaign.findings,
            graph,
            stability=stability,
        ),
        "read_only": True,
        "advisory_only": True,
    }


@app.get("/api/campaigns/{campaign_id}/advisory/history")
def campaign_advisory_history(campaign_id: str, limit: int = 50):
    assert_campaign_exists(campaign_id)
    try:
        return storage().list_advisory_focus_snapshots(campaign_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/campaigns/{campaign_id}/advisory/delta")
def campaign_advisory_delta(campaign_id: str):
    from .planner_advisory import diff_advisory_focus_snapshots

    assert_campaign_exists(campaign_id)
    snapshots = storage().list_advisory_focus_snapshots(campaign_id, limit=2)
    current = snapshots[0] if snapshots else None
    previous = snapshots[1] if len(snapshots) > 1 else None
    return diff_advisory_focus_snapshots(previous, current)


@app.get("/api/campaigns/{campaign_id}/advisory/journal")
def campaign_advisory_journal(campaign_id: str, limit: int = 100):
    from .planner_advisory import build_advisory_decision_journal

    assert_campaign_exists(campaign_id)
    try:
        snapshots = storage().list_advisory_focus_snapshots(campaign_id, limit=min(limit + 1, 500))
        return build_advisory_decision_journal(snapshots, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/campaigns/{campaign_id}/hypotheses/history")
def campaign_hypothesis_history(campaign_id: str, limit: int = 50):
    assert_campaign_exists(campaign_id)
    try:
        return storage().list_hypothesis_snapshots(campaign_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/campaigns/{campaign_id}/hypotheses/delta")
def campaign_hypothesis_delta(campaign_id: str):
    from .hypothesis_memory import diff_hypothesis_snapshots

    assert_campaign_exists(campaign_id)
    snapshots = storage().list_hypothesis_snapshots(campaign_id, limit=2)
    current = snapshots[0] if snapshots else None
    previous = snapshots[1] if len(snapshots) > 1 else None
    return diff_hypothesis_snapshots(previous, current)


@app.get("/api/campaigns/{campaign_id}/hypotheses/stability")
def campaign_hypothesis_stability(campaign_id: str, limit: int = 50):
    from .hypothesis_memory import summarize_hypothesis_stability

    assert_campaign_exists(campaign_id)
    try:
        snapshots = storage().list_hypothesis_snapshots(campaign_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return summarize_hypothesis_stability(snapshots)


@app.get("/api/campaigns/{campaign_id}/plan")
def campaign_plan(campaign_id: str):
    from .agent_registry import agent_for_action
    from .evidence_quality import build_evidence_quality
    from .knowledge_memory import build_knowledge_snapshot, rank_findings
    from .observation_graph import AdaptivePlanner
    from .planner_budget import apply_budget, budget_usage, planner_budget_from_env

    campaign = assert_campaign_exists(campaign_id)
    graph = _campaign_graph(campaign_id)
    jobs = queue()
    limits = planner_budget_from_env()
    planner_actions = AdaptivePlanner().plan(campaign, graph)
    actions = [apply_budget(item, graph, jobs, campaign.id, limits)[0] for item in planner_actions]
    usage = budget_usage(graph, jobs, campaign.id, limits)
    from .hypothesis_memory import build_hypotheses, summarize_hypothesis_stability
    from .planner_advisory import advisory_focus_fingerprint, build_advisory_planner_context

    snapshots = storage().list_hypothesis_snapshots(campaign.id, limit=50)
    stability = {
        item["finding_id"]: item
        for item in summarize_hypothesis_stability(snapshots)
    }
    advisory = build_advisory_planner_context(
        campaign,
        graph,
        stability=stability,
    )
    advisory_fingerprint = advisory_focus_fingerprint(advisory)
    storage().put_advisory_focus_snapshot(
        campaign.id,
        advisory_fingerprint,
        advisory,
    )

    return {
        "actions": [item.to_dict() for item in actions],
        "planner_actions": [item.to_dict() for item in planner_actions],
        "agents": [agent_for_action(item.kind).to_dict() for item in actions],
        "priorities": [item.to_dict() for item in rank_findings(campaign.findings, graph)],
        "hypotheses": [item.to_dict() for item in build_hypotheses(graph)],
        "advisory": advisory,
        "advisory_fingerprint": advisory_fingerprint,
        "memory": build_knowledge_snapshot(graph).to_dict(),
        "evidence_quality": [item.to_dict() for item in build_evidence_quality(graph)],
        "budget": {"limits": limits.to_dict(), "usage": usage.to_dict()},
        "read_only": True,
    }


@app.post("/api/campaigns/{campaign_id}/policy-check")
def check_policy(campaign_id: str, host: str, action: str = "automated_scan"):
    campaign, version = assert_campaign_record(campaign_id)
    receipt = policy_receipt(campaign, host, action)
    append_campaign_event(campaign.events, {"type": "policy_check", **receipt})
    campaign.updated_at = utcnow()
    save_campaign(campaign, expected_version=version)
    return receipt


@app.post("/api/campaigns/{campaign_id}/policy-verify")
def verify_campaign_policy_receipt(campaign_id: str, receipt: dict[str, Any] = Body(...)):
    assert_campaign_exists(campaign_id)
    return verify_policy_receipt(receipt)


def _pending_campaign_start_request(campaign: Campaign) -> str | None:
    return pending_request_id(
        campaign.events,
        requested_type="campaign_start_requested",
        completed_type="campaign_started",
    )


def _record_campaign_start_intent(
    campaign: Campaign,
    version: int,
    *,
    request_id: str,
    receipt: dict[str, Any],
) -> int:
    if any(
        event.get("type") == "campaign_start_requested"
        and event.get("request_id") == request_id
        for event in campaign.events
    ):
        return version
    append_campaign_event(
        campaign.events,
        {
            "type": "campaign_start_requested",
            "request_id": request_id,
            "at": utcnow(),
            "policy": receipt,
        },
    )
    campaign.updated_at = utcnow()
    return save_campaign(campaign, expected_version=version)


def _reconcile_campaign_started(
    campaign_id: str,
    job: dict[str, Any],
    *,
    request_id: str,
    receipt: dict[str, Any],
    attempts: int = 3,
) -> Campaign:
    for _ in range(attempts):
        campaign, version = assert_campaign_record(campaign_id)
        if any(
            event.get("type") == "campaign_started"
            and event.get("request_id") == request_id
            and event.get("job_id") == job["id"]
            for event in campaign.events
        ):
            return campaign
        _reject_cancelled_campaign(campaign)
        if campaign.state not in {
            CampaignState.ready,
            CampaignState.failed,
            CampaignState.running,
        }:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot reconcile campaign start from {campaign.state.value}",
            )
        append_campaign_event(
            campaign.events,
            {
                "type": "campaign_started",
                "request_id": request_id,
                "at": utcnow(),
                "policy": receipt,
                "job_id": job["id"],
            },
        )
        campaign.state = CampaignState.running
        campaign.updated_at = utcnow()
        try:
            save_campaign(campaign, expected_version=version)
            return campaign
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
    raise HTTPException(
        status_code=409,
        detail="Campaign start job queued but audit reconciliation conflicted; retry safely",
    )


@app.post("/api/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: str):
    campaign, version = assert_campaign_record(campaign_id)
    if campaign.state not in {CampaignState.ready, CampaignState.failed}:
        raise HTTPException(status_code=409, detail=f"Cannot start from {campaign.state}")
    host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
    receipt = policy_receipt(campaign, host, "automated_scan")
    if not receipt["allowed"]:
        append_campaign_event(campaign.events, {"type": "campaign_blocked", "at": utcnow(), "policy": receipt})
        campaign.updated_at = utcnow()
        save_campaign(campaign, expected_version=version)
        raise HTTPException(status_code=403, detail={"message": "Policy blocked campaign", "receipt": receipt})

    payload = sanitized_scan_payload(campaign, receipt, job_kind="strix_scan")
    request_id = _pending_campaign_start_request(campaign) or str(uuid4())
    _record_campaign_start_intent(
        campaign,
        version,
        request_id=request_id,
        receipt=receipt,
    )
    job = queue().enqueue(
        campaign.id,
        "strix_scan",
        payload,
        max_attempts=2,
        dedupe_key=f"api:start:{request_id}",
    )
    campaign = _reconcile_campaign_started(
        campaign.id,
        job,
        request_id=request_id,
        receipt=receipt,
    )
    return {
        "campaign_id": campaign.id,
        "state": campaign.state,
        "policy": receipt,
        "job": job,
        "request_id": request_id,
        "audit_reconciled": True,
    }


@app.post("/api/campaigns/{campaign_id}/cancel")
def cancel_campaign(campaign_id: str):
    campaign, version = assert_campaign_record(campaign_id)
    jobs = queue()

    if campaign.state == CampaignState.completed:
        raise HTTPException(status_code=409, detail="Completed campaign cannot be cancelled")
    if campaign.state == CampaignState.cancelled:
        statuses = jobs.campaign_job_status_counts(campaign.id)
        return {
            "campaign_id": campaign.id,
            "state": campaign.state,
            "cancelled_queued_jobs": 0,
            "running_jobs": statuses["running"],
            "running_jobs_not_forcibly_terminated": bool(statuses["running"]),
        }

    campaign.state = CampaignState.cancelled
    campaign.updated_at = utcnow()
    append_campaign_event(campaign.events, {"type": "campaign_cancelled", "at": utcnow()})
    save_campaign(campaign, expected_version=version)

    cancelled = jobs.cancel_queued(campaign.id)
    statuses = jobs.campaign_job_status_counts(campaign.id)
    return {
        "campaign_id": campaign.id,
        "state": campaign.state,
        "cancelled_queued_jobs": cancelled,
        "running_jobs": statuses["running"],
        "running_jobs_not_forcibly_terminated": bool(statuses["running"]),
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = queue().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/recovery/readiness")
def recovery_readiness_gate():
    from .recovery_readiness import (
        current_recovery_readiness,
        record_recovery_readiness,
    )

    dependencies = dependency_readiness()
    store = storage()
    result = current_recovery_readiness(
        store,
        queue(),
        dependencies=dependencies,
    )
    return record_recovery_readiness(store, result)


@app.get("/api/recovery/readiness/history")
def recovery_readiness_history(limit: int = 100):
    from .recovery_readiness import recovery_readiness_history as build_history

    try:
        return build_history(storage(), limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/recovery/queue")
def queue_recovery_assessment():
    assessment = queue().recovery_assessment()
    return {
        **assessment,
        "read_only": True,
        "automatic_requeue": False,
        "automatic_job_creation": False,
        "automatic_mutation": False,
        "payloads_exposed": False,
        "raw_errors_exposed": False,
    }


@app.get("/api/jobs/{job_id}/transitions")
def get_job_transition_audit(job_id: str):
    jobs = queue()
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    verification = jobs.verify_job_transitions(job_id)
    events = jobs.job_transitions(job_id)
    return {
        "job_id": job_id,
        "campaign_id": job["campaign_id"],
        "job_kind": job["kind"],
        "verification": verification,
        "transitions": [
            {
                key: event.get(key)
                for key in (
                    "seq",
                    "from_status",
                    "to_status",
                    "at",
                    "previous_hash",
                    "event_hash",
                )
            }
            for event in events
        ],
        "read_only": True,
        "payload_exposed": False,
        "errors_exposed": False,
        "worker_identity_exposed": False,
    }


@app.get("/api/jobs/{job_id}/provenance")
def get_job_provenance_status(job_id: str):
    job = queue().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    campaign = assert_campaign_exists(str(job["campaign_id"]))
    verification = verify_job_provenance(job, campaign)
    return {
        "job_id": job["id"],
        "campaign_id": campaign.id,
        "job_kind": job["kind"],
        "provenance": verification,
        "read_only": True,
        "payload_exposed": False,
        "fail_closed_capable": True,
    }


def _validation_request_id(finding_id: str) -> str:
    return f"validation:{finding_id}"


def _reconcile_validation_queued(
    campaign_id: str,
    finding_id: str,
    job: dict[str, Any],
    *,
    request_id: str,
    attempts: int = 3,
) -> Finding:
    for _ in range(attempts):
        campaign, version = assert_campaign_record(campaign_id)
        _reject_new_findings_for_closed_campaign(campaign)
        current = next((item for item in campaign.findings if item.id == finding_id), None)
        if current is None:
            raise HTTPException(status_code=409, detail="Finding disappeared during validation queue reconciliation")
        if current.status != "validation_required":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot queue validation for finding in {current.status} state",
            )
        if has_event(
            campaign.events,
            "validation_queued",
            identity={"finding_id": finding_id, "request_id": request_id, "job_id": job["id"]},
        ):
            return current
        append_campaign_event(
            campaign.events,
            {
                "type": "validation_queued",
                "finding_id": finding_id,
                "request_id": request_id,
                "job_id": job["id"],
                "at": utcnow(),
            },
        )
        campaign.updated_at = utcnow()
        try:
            save_campaign(campaign, expected_version=version)
            return current
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
    raise HTTPException(
        status_code=409,
        detail="Validation job queued but campaign audit reconciliation conflicted; retry safely",
    )


@app.post("/api/campaigns/{campaign_id}/findings", response_model=Finding)
def add_finding(campaign_id: str, finding: Finding):
    campaign, version = assert_campaign_record(campaign_id)
    _reject_new_findings_for_closed_campaign(campaign)
    host = (urlparse(finding.asset).hostname or finding.asset.split(":")[0]).lower()
    if not is_host_allowed(host, campaign.target.rules.allowed_targets, campaign.target.rules.denied_targets):
        raise HTTPException(status_code=403, detail="Finding asset is outside campaign scope")

    request_id = _validation_request_id(finding.id)
    existing = next((item for item in campaign.findings if item.id == finding.id), None)
    if existing:
        candidate = finding.model_copy(update={"status": existing.status, "validated_by": existing.validated_by})
        if candidate.model_dump(mode="json") != existing.model_dump(mode="json"):
            raise HTTPException(status_code=409, detail="Finding id already exists with different content")
        if has_event(
            campaign.events,
            "validation_queued",
            identity={"finding_id": finding.id, "request_id": request_id},
        ):
            return existing
        if not has_event(
            campaign.events,
            "validation_requested",
            identity={"finding_id": finding.id, "request_id": request_id},
        ):
            append_campaign_event(
                campaign.events,
                {
                    "type": "validation_requested",
                    "finding_id": finding.id,
                    "request_id": request_id,
                    "at": utcnow(),
                },
            )
            campaign.updated_at = utcnow()
            save_campaign(campaign, expected_version=version)
    else:
        finding.status = "validation_required"
        campaign.findings.append(finding)
        campaign.state = CampaignState.validating
        campaign.updated_at = utcnow()
        append_campaign_event(
            campaign.events,
            {"type": "finding_received", "finding_id": finding.id, "at": utcnow()},
        )
        append_campaign_event(
            campaign.events,
            {
                "type": "validation_requested",
                "finding_id": finding.id,
                "request_id": request_id,
                "at": utcnow(),
            },
        )
        save_campaign(campaign, expected_version=version)

    latest = assert_campaign_exists(campaign.id)
    _reject_new_findings_for_closed_campaign(latest)
    current = next((item for item in latest.findings if item.id == finding.id), None)
    if current is None or current.status != "validation_required":
        raise HTTPException(status_code=409, detail="Finding is no longer awaiting validation")

    validation_job = queue().enqueue(
        campaign.id,
        "independent_validation",
        attach_job_provenance(
            {"campaign_id": campaign.id, "finding_id": finding.id, "asset": current.asset},
            latest,
            job_kind="independent_validation",
            action="validate",
        ),
        max_attempts=2,
        dedupe_key=request_id,
    )
    return _reconcile_validation_queued(
        campaign.id,
        finding.id,
        validation_job,
        request_id=request_id,
    )


def _record_report_request(
    campaign: Campaign,
    version: int,
    *,
    request_id: str,
    platform: str,
    purpose: str,
) -> int:
    identity = {
        "request_id": request_id,
        "platform": platform,
        "purpose": purpose,
    }
    if has_event(campaign.events, "report_requested", identity=identity):
        return version
    append_campaign_event(
        campaign.events,
        {
            "type": "report_requested",
            **identity,
            "at": utcnow(),
        },
    )
    campaign.updated_at = utcnow()
    return save_campaign(campaign, expected_version=version)


def _reconcile_report_job(
    campaign_id: str,
    job: dict[str, Any],
    *,
    request_id: str,
    platform: str,
    purpose: str,
    completion_type: str,
    mark_completed: bool = False,
    attempts: int = 3,
) -> Campaign:
    identity = {
        "request_id": request_id,
        "platform": platform,
        "purpose": purpose,
        "job_id": job["id"],
    }
    for _ in range(attempts):
        campaign, version = assert_campaign_record(campaign_id)
        _reject_cancelled_campaign(campaign)
        if has_event(campaign.events, completion_type, identity=identity):
            return campaign
        append_campaign_event(
            campaign.events,
            {
                "type": completion_type,
                **identity,
                "report_job_id": job["id"],
                "at": utcnow(),
            },
        )
        if mark_completed:
            campaign.state = CampaignState.completed
        campaign.updated_at = utcnow()
        try:
            save_campaign(campaign, expected_version=version)
            return campaign
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
    raise HTTPException(
        status_code=409,
        detail="Report job queued but campaign audit reconciliation conflicted; retry safely",
    )


def _ensure_completion_report(campaign: Campaign, version: int) -> Campaign:
    request_id = "report:generic:completed"
    platform = "generic"
    purpose = "campaign_completion"
    if has_event(
        campaign.events,
        "campaign_completed",
        identity={
            "request_id": request_id,
            "platform": platform,
            "purpose": purpose,
        },
    ):
        return campaign

    if not has_event(
        campaign.events,
        "report_requested",
        identity={
            "request_id": request_id,
            "platform": platform,
            "purpose": purpose,
        },
    ):
        append_campaign_event(
            campaign.events,
            {
                "type": "report_requested",
                "request_id": request_id,
                "platform": platform,
                "purpose": purpose,
                "at": utcnow(),
            },
        )
        campaign.state = CampaignState.completed
        campaign.updated_at = utcnow()
        save_campaign(campaign, expected_version=version)
    elif campaign.state != CampaignState.completed:
        campaign.state = CampaignState.completed
        campaign.updated_at = utcnow()
        save_campaign(campaign, expected_version=version)

    latest = assert_campaign_exists(campaign.id)
    _reject_cancelled_campaign(latest)
    report_job = queue().enqueue(
        campaign.id,
        "report",
        attach_job_provenance(
            {"campaign_id": campaign.id, "platform": platform},
            latest,
            job_kind="report",
            action="report",
        ),
        max_attempts=2,
        dedupe_key=request_id,
    )
    return _reconcile_report_job(
        campaign.id,
        report_job,
        request_id=request_id,
        platform=platform,
        purpose=purpose,
        completion_type="campaign_completed",
        mark_completed=True,
    )


@app.post("/api/campaigns/{campaign_id}/findings/{finding_id}/validate")
def validate_finding(campaign_id: str, finding_id: str, confirmed: bool, validator: str = "independent-validator"):
    campaign, version = assert_campaign_record(campaign_id)
    _reject_cancelled_campaign(campaign)
    finding = next((x for x in campaign.findings if x.id == finding_id), None)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if validator == finding.discovered_by:
        raise HTTPException(status_code=409, detail="Discovery agent cannot validate its own finding")
    if not _has_evidence_backed_independent_validation(campaign_id, finding):
        raise HTTPException(
            status_code=409,
            detail="Finding requires evidence-backed independent validation before resolution",
        )

    desired_status = "confirmed" if confirmed else "rejected"
    if finding.status == desired_status and finding.validated_by == validator:
        if campaign.findings and all(item.status in {"confirmed", "rejected"} for item in campaign.findings):
            completed = _ensure_completion_report(campaign, version)
            return next(item for item in completed.findings if item.id == finding_id)
        return finding
    if finding.status in {"confirmed", "rejected"} and finding.status != desired_status:
        raise HTTPException(status_code=409, detail="Finding already has a conflicting validation result")

    finding.status = desired_status
    finding.validated_by = validator
    campaign.updated_at = utcnow()
    append_campaign_event(
        campaign.events,
        {
            "type": "finding_validated",
            "finding_id": finding.id,
            "confirmed": confirmed,
            "validator": validator,
            "at": utcnow(),
        },
    )
    should_complete = bool(
        campaign.findings
        and all(item.status in {"confirmed", "rejected"} for item in campaign.findings)
    )
    if should_complete:
        request_id = "report:generic:completed"
        append_campaign_event(
            campaign.events,
            {
                "type": "report_requested",
                "request_id": request_id,
                "platform": "generic",
                "purpose": "campaign_completion",
                "at": utcnow(),
            },
        )
        campaign.state = CampaignState.completed
    save_campaign(campaign, expected_version=version)

    if should_complete:
        latest, latest_version = assert_campaign_record(campaign.id)
        completed = _ensure_completion_report(latest, latest_version)
        return next(item for item in completed.findings if item.id == finding_id)
    return finding


@app.post("/api/campaigns/{campaign_id}/reports")
def queue_report(campaign_id: str, platform: Literal["generic", "hackerone", "bugcrowd"] = "generic"):
    campaign, version = assert_campaign_record(campaign_id)
    _reject_cancelled_campaign(campaign)
    purpose = "manual"
    request_id = pending_request_id(
        campaign.events,
        requested_type="report_requested",
        completed_type="report_queued",
        identity={"platform": platform, "purpose": purpose},
    ) or str(uuid4())
    _record_report_request(
        campaign,
        version,
        request_id=request_id,
        platform=platform,
        purpose=purpose,
    )
    latest = assert_campaign_exists(campaign.id)
    _reject_cancelled_campaign(latest)
    job = queue().enqueue(
        campaign.id,
        "report",
        attach_job_provenance(
            {"campaign_id": campaign.id, "platform": platform},
            latest,
            job_kind="report",
            action="report",
        ),
        max_attempts=2,
        dedupe_key=f"report:{platform}:{request_id}",
    )
    _reconcile_report_job(
        campaign.id,
        job,
        request_id=request_id,
        platform=platform,
        purpose=purpose,
        completion_type="report_queued",
    )
    return job


@app.post("/api/campaigns/{campaign_id}/artifacts")
def add_text_artifact(campaign_id: str, evidence: EvidenceInput = Body(...)):
    campaign, version = assert_campaign_record(campaign_id)
    if evidence.finding_id and not any(f.id == evidence.finding_id for f in campaign.findings):
        raise HTTPException(status_code=404, detail="Finding not found")
    content = evidence.content.encode("utf-8")
    idempotency_key = _stable_key(
        "api-artifact",
        evidence.kind,
        evidence.finding_id or "",
        evidence.media_type,
        hashlib.sha256(content).hexdigest(),
    )
    try:
        artifact = storage().put_artifact(
            campaign_id,
            evidence.kind,
            content,
            media_type=evidence.media_type,
            finding_id=evidence.finding_id,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not any(event.get("type") == "artifact_stored" and event.get("artifact_id") == artifact["id"] for event in campaign.events):
        append_campaign_event(campaign.events, {"type": "artifact_stored", "artifact_id": artifact["id"], "kind": evidence.kind, "at": utcnow()})
        campaign.updated_at = utcnow()
        save_campaign(campaign, expected_version=version)
    return artifact


@app.get("/api/campaigns/{campaign_id}/artifacts")
def list_artifacts(campaign_id: str):
    assert_campaign_exists(campaign_id)
    return storage().list_artifacts(campaign_id)


@app.get("/api/campaigns/{campaign_id}/artifacts/{artifact_id}")
def download_artifact(campaign_id: str, artifact_id: str):
    assert_campaign_exists(campaign_id)
    try:
        metadata, content = storage().read_artifact(campaign_id, artifact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Artifact not found") from exc
    except ArtifactIntegrityError as exc:
        raise HTTPException(status_code=409, detail=f"Artifact integrity verification failed: {exc}") from exc
    return Response(
        content=content,
        media_type=metadata["media_type"],
        headers={
            "X-Content-SHA256": metadata["sha256"],
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{artifact_id}"',
        },
    )


from .browser import router as browser_router  # noqa: E402
from .campaign_control import router as campaign_control_router  # noqa: E402
from .coverage import router as coverage_router  # noqa: E402
from .decision_timeline import router as decision_timeline_router  # noqa: E402
from .evidence_quality import router as evidence_quality_router  # noqa: E402
from .finding_cluster_consensus import router as finding_cluster_consensus_router  # noqa: E402
from .finding_cluster_saturation import router as finding_cluster_saturation_router  # noqa: E402
from .finding_intelligence import router as finding_intelligence_router  # noqa: E402
from .finding_correlation import router as finding_correlation_router  # noqa: E402
from .finding_readiness import router as finding_readiness_router  # noqa: E402
from .metrics import router as metrics_router  # noqa: E402
from .operational_alerts import router as alerts_router  # noqa: E402
from .operations_dashboard import router as operations_dashboard_router  # noqa: E402
from .report_readiness import router as report_readiness_router  # noqa: E402
from .review_queue import router as review_queue_router  # noqa: E402
from .slo import router as slo_router  # noqa: E402

app.include_router(browser_router)
app.include_router(campaign_control_router)
app.include_router(coverage_router)
app.include_router(decision_timeline_router)
app.include_router(evidence_quality_router)
app.include_router(finding_correlation_router)
app.include_router(finding_cluster_consensus_router)
app.include_router(finding_cluster_saturation_router)
app.include_router(finding_intelligence_router)
app.include_router(finding_readiness_router)
app.include_router(metrics_router)
app.include_router(alerts_router)
app.include_router(operations_dashboard_router)
app.include_router(report_readiness_router)
app.include_router(review_queue_router)
app.include_router(slo_router)
