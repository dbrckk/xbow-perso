from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from fnmatch import fnmatch
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, HttpUrl, model_validator

from .auth import AuthError, require_api_token
from .jobqueue import JobQueue
from .storage import ArtifactIntegrityError, Storage

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


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def storage() -> Storage:
    return Storage()


def queue() -> JobQueue:
    return JobQueue()


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
        host = (urlparse(str(self.primary_url)).hostname or "").lower()
        if not host:
            raise ValueError("primary_url has no hostname")
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


def save_campaign(campaign: Campaign) -> None:
    storage().save_campaign(campaign.model_dump(mode="json"))


def assert_campaign_exists(campaign_id: str) -> Campaign:
    document = storage().get_campaign(campaign_id)
    if not document:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return Campaign.model_validate(document)


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
    action_blocked = blocked_actions.get(action, False)
    return {
        "allowed": allowed and not action_blocked,
        "host": host,
        "action": action,
        "scope_allowed": allowed,
        "action_blocked": action_blocked,
        "authorization_reference": rules.authorization_reference,
        "timestamp": utcnow(),
    }


def sanitized_scan_payload(campaign: Campaign, receipt: dict[str, Any]) -> dict[str, Any]:
    """Immutable worker input. Secrets/credential notes are intentionally excluded."""
    return {
        "campaign_id": campaign.id,
        "target": str(campaign.target.primary_url),
        "policy": receipt,
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


@app.get("/health")
def health():
    try:
        database = queue().health()
    except Exception:
        database = {"ok": False, "database": "unavailable"}
    payload = {"ok": bool(database.get("ok")), "service": "xbow-perso", "version": app.version, "database": database}
    if not payload["ok"]:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.post("/api/campaigns", response_model=Campaign)
def create_campaign(target: TargetInput):
    campaign = Campaign(target=target, state=CampaignState.ready)
    campaign.events.append({"type": "campaign_created", "at": utcnow()})
    save_campaign(campaign)
    return campaign


@app.get("/api/campaigns", response_model=list[Campaign])
def list_campaigns():
    return [Campaign.model_validate(x) for x in storage().list_campaigns()]


@app.get("/api/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str):
    return assert_campaign_exists(campaign_id)


@app.post("/api/campaigns/{campaign_id}/policy-check")
def check_policy(campaign_id: str, host: str, action: str = "automated_scan"):
    campaign = assert_campaign_exists(campaign_id)
    receipt = policy_receipt(campaign, host, action)
    campaign.events.append({"type": "policy_check", **receipt})
    campaign.updated_at = utcnow()
    save_campaign(campaign)
    return receipt


@app.post("/api/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: str):
    campaign = assert_campaign_exists(campaign_id)
    if campaign.state not in {CampaignState.ready, CampaignState.failed}:
        raise HTTPException(status_code=409, detail=f"Cannot start from {campaign.state}")
    host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
    receipt = policy_receipt(campaign, host, "automated_scan")
    if not receipt["allowed"]:
        campaign.events.append({"type": "campaign_blocked", "at": utcnow(), "policy": receipt})
        campaign.updated_at = utcnow()
        save_campaign(campaign)
        raise HTTPException(status_code=403, detail={"message": "Policy blocked campaign", "receipt": receipt})

    payload = sanitized_scan_payload(campaign, receipt)
    job = queue().enqueue(campaign.id, "strix_scan", payload, max_attempts=2)
    campaign.state = CampaignState.running
    campaign.updated_at = utcnow()
    campaign.events.append({"type": "campaign_started", "at": utcnow(), "policy": receipt, "job_id": job["id"]})
    save_campaign(campaign)
    return {"campaign_id": campaign.id, "state": campaign.state, "policy": receipt, "job": job}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = queue().get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/campaigns/{campaign_id}/findings", response_model=Finding)
def add_finding(campaign_id: str, finding: Finding):
    campaign = assert_campaign_exists(campaign_id)
    host = (urlparse(finding.asset).hostname or finding.asset.split(":")[0]).lower()
    if not is_host_allowed(host, campaign.target.rules.allowed_targets, campaign.target.rules.denied_targets):
        raise HTTPException(status_code=403, detail="Finding asset is outside campaign scope")
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
    )
    campaign.events.append({"type": "validation_queued", "finding_id": finding.id, "job_id": validation_job["id"], "at": utcnow()})
    save_campaign(campaign)
    return finding


@app.post("/api/campaigns/{campaign_id}/findings/{finding_id}/validate")
def validate_finding(campaign_id: str, finding_id: str, confirmed: bool, validator: str = "independent-validator"):
    campaign = assert_campaign_exists(campaign_id)
    finding = next((x for x in campaign.findings if x.id == finding_id), None)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    if validator == finding.discovered_by:
        raise HTTPException(status_code=409, detail="Discovery agent cannot validate its own finding")
    finding.status = "confirmed" if confirmed else "rejected"
    finding.validated_by = validator
    campaign.updated_at = utcnow()
    campaign.events.append({"type": "finding_validated", "finding_id": finding.id, "confirmed": confirmed, "validator": validator, "at": utcnow()})
    if campaign.findings and all(item.status in {"confirmed", "rejected"} for item in campaign.findings):
        campaign.state = CampaignState.completed
        report_job = queue().enqueue(campaign.id, "report", {"campaign_id": campaign.id, "platform": "generic"}, max_attempts=2)
        campaign.events.append({"type": "campaign_completed", "report_job_id": report_job["id"], "at": utcnow()})
    save_campaign(campaign)
    return finding


@app.post("/api/campaigns/{campaign_id}/reports")
def queue_report(campaign_id: str, platform: Literal["generic", "hackerone", "bugcrowd"] = "generic"):
    campaign = assert_campaign_exists(campaign_id)
    job = queue().enqueue(campaign.id, "report", {"campaign_id": campaign.id, "platform": platform}, max_attempts=2)
    campaign.events.append({"type": "report_queued", "platform": platform, "job_id": job["id"], "at": utcnow()})
    campaign.updated_at = utcnow()
    save_campaign(campaign)
    return job


@app.post("/api/campaigns/{campaign_id}/artifacts")
def add_text_artifact(campaign_id: str, evidence: EvidenceInput = Body(...)):
    campaign = assert_campaign_exists(campaign_id)
    if evidence.finding_id and not any(f.id == evidence.finding_id for f in campaign.findings):
        raise HTTPException(status_code=404, detail="Finding not found")
    try:
        artifact = storage().put_artifact(
            campaign_id,
            evidence.kind,
            evidence.content.encode("utf-8"),
            media_type=evidence.media_type,
            finding_id=evidence.finding_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    campaign.events.append({"type": "artifact_stored", "artifact_id": artifact["id"], "kind": evidence.kind, "at": utcnow()})
    campaign.updated_at = utcnow()
    save_campaign(campaign)
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


# Imported last to avoid circular imports: browser policy helpers intentionally
# reuse the canonical Campaign and scope models defined above.
from .browser import router as browser_router  # noqa: E402

app.include_router(browser_router)
