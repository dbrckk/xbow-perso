from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from fnmatch import fnmatch
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator

app = FastAPI(title="xbow-perso", version="0.1.0")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


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


CAMPAIGNS: dict[str, Campaign] = {}


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


def assert_campaign_exists(campaign_id: str) -> Campaign:
    campaign = CAMPAIGNS.get(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


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


@app.get("/health")
def health():
    return {"ok": True, "service": "xbow-perso", "version": app.version}


@app.post("/api/campaigns", response_model=Campaign)
def create_campaign(target: TargetInput):
    campaign = Campaign(target=target, state=CampaignState.ready)
    campaign.events.append({"type": "campaign_created", "at": utcnow()})
    CAMPAIGNS[campaign.id] = campaign
    return campaign


@app.get("/api/campaigns", response_model=list[Campaign])
def list_campaigns():
    return list(CAMPAIGNS.values())


@app.get("/api/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str):
    return assert_campaign_exists(campaign_id)


@app.post("/api/campaigns/{campaign_id}/policy-check")
def check_policy(campaign_id: str, host: str, action: str = "automated_scan"):
    campaign = assert_campaign_exists(campaign_id)
    receipt = policy_receipt(campaign, host, action)
    campaign.events.append({"type": "policy_check", **receipt})
    return receipt


@app.post("/api/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: str):
    campaign = assert_campaign_exists(campaign_id)
    if campaign.state not in {CampaignState.ready, CampaignState.failed}:
        raise HTTPException(status_code=409, detail=f"Cannot start from {campaign.state}")
    host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
    receipt = policy_receipt(campaign, host, "automated_scan")
    if not receipt["allowed"]:
        raise HTTPException(status_code=403, detail={"message": "Policy blocked campaign", "receipt": receipt})
    campaign.state = CampaignState.running
    campaign.updated_at = utcnow()
    campaign.events.append({"type": "campaign_started", "at": utcnow(), "policy": receipt})
    # Worker dispatch is deliberately adapter-based; see worker.py.
    return {"campaign_id": campaign.id, "state": campaign.state, "policy": receipt}


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
    campaign.events.append({"type": "finding_validated", "finding_id": finding.id, "confirmed": confirmed, "at": utcnow()})
    return finding
