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

from .api_rate_limit import api_rate_limit_middleware
from .auth import AuthError, require_api_token
from .queue_backend import QueueBackend, create_queue
from .readiness import readiness as dependency_readiness
from .storage import ArtifactIntegrityError, CampaignConflictError
from .storage_backend import StorageBackend, create_storage
from .validation_state import has_observed_independent_validation

app = FastAPI(title="xbow-perso", version="0.4.0")


@app.middleware("http")
async def authenticate_control_api(request: Request, call_next):
    if request.url.path.startswith("/api/") or request.url.path == "/api":
        try:
            require_api_token(request)
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


def _has_observed_independent_validation(campaign_id: str, finding: Finding) -> bool:
    graph = _campaign_graph(campaign_id)
    return has_observed_independent_validation(graph, f"finding:{finding.id}")


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
    return {
        "allowed": allowed and not action_blocked,
        "host": host,
        "action": action,
        "action_known": action_known,
        "scope_allowed": allowed,
        "action_blocked": action_blocked,
        "authorization_reference": rules.authorization_reference,
        "timestamp": utcnow(),
    }


def sanitized_scan_payload(campaign: Campaign, receipt: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic worker input suitable for queue idempotency.

    The audit receipt keeps its timestamp in campaign events/API responses, but
    transient timestamps must never enter a deduplicated queue payload.
    """
    stable_receipt = {key: value for key, value in receipt.items() if key != "timestamp"}
    return {
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


@app.get("/api/capabilities")
def system_capabilities():
    return {
        "campaign_control": {
            "scope_enforcement": True,
            "durable_queue": True,
            "artifact_integrity": "sha256",
            "optimistic_campaign_versioning": True,
        },
        "execution": {
            "strix_scanning": "gated",
            "http_validation": "gated",
            "browser_automation": "gated",
            "default_mode": "dry_run",
            "arbitrary_shell_jobs": False,
        },
        "reasoning": {
            "adaptive_planning": "advisory",
            "observation_graph": True,
            "knowledge_memory": True,
            "hypothesis_engine": "read_only",
            "finding_triage": "read_only",
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
        },
    }


@app.get("/api/agents")
def list_agents():
    from .agent_registry import public_agent_catalog
    return public_agent_catalog()


@app.post("/api/campaigns", response_model=Campaign)
def create_campaign(target: TargetInput):
    campaign = Campaign(target=target, state=CampaignState.ready)
    campaign.events.append({"type": "campaign_created", "at": utcnow()})
    save_campaign(campaign, expected_version=0)
    return campaign


@app.get("/api/campaigns", response_model=list[Campaign])
def list_campaigns():
    return [Campaign.model_validate(x) for x in storage().list_campaigns()]


@app.get("/api/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str):
    return assert_campaign_exists(campaign_id)


@app.get("/api/campaigns/{campaign_id}/observations")
def list_campaign_observations(campaign_id: str):
    assert_campaign_exists(campaign_id)
    return storage().list_observations(campaign_id)


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
    from .knowledge_memory import build_knowledge_snapshot, rank_findings
    from .observation_graph import AdaptivePlanner
    from .planner_budget import PlannerBudget, apply_budget, budget_usage

    campaign = assert_campaign_exists(campaign_id)
    graph = _campaign_graph(campaign_id)
    jobs = queue()
    limits = PlannerBudget()
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
        "budget": {"limits": limits.to_dict(), "usage": usage.to_dict()},
        "read_only": True,
    }


@app.post("/api/campaigns/{campaign_id}/policy-check")
def check_policy(campaign_id: str, host: str, action: str = "automated_scan"):
    campaign, version = assert_campaign_record(campaign_id)
    receipt = policy_receipt(campaign, host, action)
    campaign.events.append({"type": "policy_check", **receipt})
    campaign.updated_at = utcnow()
    save_campaign(campaign, expected_version=version)
    return receipt


@app.post("/api/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: str):
    campaign, version = assert_campaign_record(campaign_id)
    if campaign.state not in {CampaignState.ready, CampaignState.failed}:
        raise HTTPException(status_code=409, detail=f"Cannot start from {campaign.state}")
    host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
    receipt = policy_receipt(campaign, host, "automated_scan")
    if not receipt["allowed"]:
        campaign.events.append({"type": "campaign_blocked", "at": utcnow(), "policy": receipt})
        campaign.updated_at = utcnow()
        save_campaign(campaign, expected_version=version)
        raise HTTPException(status_code=403, detail={"message": "Policy blocked campaign", "receipt": receipt})

    payload = sanitized_scan_payload(campaign, receipt)
    job = queue().enqueue(
        campaign.id,
        "strix_scan",
        payload,
        max_attempts=2,
        dedupe_key=f"api:start:v{version}",
    )
    campaign.state = CampaignState.running
    campaign.updated_at = utcnow()
    campaign.events.append({"type": "campaign_started", "at": utcnow(), "policy": receipt, "job_id": job["id"]})
    save_campaign(campaign, expected_version=version)
    return {"campaign_id": campaign.id, "state": campaign.state, "policy": receipt, "job": job}


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
    campaign.events.append({"type": "campaign_cancelled", "at": utcnow()})
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


@app.post("/api/campaigns/{campaign_id}/findings", response_model=Finding)
def add_finding(campaign_id: str, finding: Finding):
    campaign, version = assert_campaign_record(campaign_id)
    _reject_new_findings_for_closed_campaign(campaign)
    host = (urlparse(finding.asset).hostname or finding.asset.split(":")[0]).lower()
    if not is_host_allowed(host, campaign.target.rules.allowed_targets, campaign.target.rules.denied_targets):
        raise HTTPException(status_code=403, detail="Finding asset is outside campaign scope")

    existing = next((item for item in campaign.findings if item.id == finding.id), None)
    if existing:
        candidate = finding.model_copy(update={"status": existing.status, "validated_by": existing.validated_by})
        if candidate.model_dump(mode="json") != existing.model_dump(mode="json"):
            raise HTTPException(status_code=409, detail="Finding id already exists with different content")
        return existing

    finding.status = "validation_required"
    campaign.findings.append(finding)
    campaign.state = CampaignState.validating
    campaign.updated_at = utcnow()
    campaign.events.append({"type": "finding_received", "finding_id": finding.id, "at": utcnow()})
    validation_job = queue().enqueue(
        campaign.id,
        "independent_validation",
        {"campaign_id": campaign.id, "finding_id": finding.id, "asset": finding.asset},
        max_attempts=2,
        dedupe_key=f"validation:{finding.id}",
    )
    campaign.events.append({"type": "validation_queued", "finding_id": finding.id, "job_id": validation_job["id"], "at": utcnow()})
    save_campaign(campaign, expected_version=version)
    return finding


@app.post("/api/campaigns/{campaign_id}/findings/{finding_id}/validate")
def validate_finding(campaign_id: str, finding_id: str, confirmed: bool, validator: str = "independent-validator"):
    campaign, version = assert_campaign_record(campaign_id)
    _reject_cancelled_campaign(campaign)
    finding = next((x for x in campaign.findings if x.id == finding_id), None)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if validator == finding.discovered_by:
        raise HTTPException(status_code=409, detail="Discovery agent cannot validate its own finding")
    if not _has_observed_independent_validation(campaign_id, finding):
        raise HTTPException(status_code=409, detail="Finding requires observed independent validation evidence before resolution")

    desired_status = "confirmed" if confirmed else "rejected"
    if finding.status == desired_status and finding.validated_by == validator:
        return finding
    if finding.status in {"confirmed", "rejected"} and finding.status != desired_status:
        raise HTTPException(status_code=409, detail="Finding already has a conflicting validation result")

    finding.status = desired_status
    finding.validated_by = validator
    campaign.updated_at = utcnow()
    campaign.events.append({"type": "finding_validated", "finding_id": finding.id, "confirmed": confirmed, "validator": validator, "at": utcnow()})
    if campaign.findings and all(item.status in {"confirmed", "rejected"} for item in campaign.findings):
        campaign.state = CampaignState.completed
        report_job = queue().enqueue(
            campaign.id,
            "report",
            {"campaign_id": campaign.id, "platform": "generic"},
            max_attempts=2,
            dedupe_key="report:generic:completed",
        )
        campaign.events.append({"type": "campaign_completed", "report_job_id": report_job["id"], "at": utcnow()})
    save_campaign(campaign, expected_version=version)
    return finding


@app.post("/api/campaigns/{campaign_id}/reports")
def queue_report(campaign_id: str, platform: Literal["generic", "hackerone", "bugcrowd"] = "generic"):
    campaign, version = assert_campaign_record(campaign_id)
    _reject_cancelled_campaign(campaign)
    job = queue().enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": platform},
        max_attempts=2,
        dedupe_key=f"report:{platform}:v{version}",
    )
    campaign.events.append({"type": "report_queued", "platform": platform, "job_id": job["id"], "at": utcnow()})
    campaign.updated_at = utcnow()
    save_campaign(campaign, expected_version=version)
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
        campaign.events.append({"type": "artifact_stored", "artifact_id": artifact["id"], "kind": evidence.kind, "at": utcnow()})
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
from .coverage import router as coverage_router  # noqa: E402

app.include_router(browser_router)
app.include_router(coverage_router)
