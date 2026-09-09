from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .jobqueue import JobQueue
from .storage import CampaignConflictError, Storage

router = APIRouter()


class BrowserPolicyError(RuntimeError):
    pass


class BrowserStep(BaseModel):
    operation: Literal["navigate", "click", "fill", "wait_for", "screenshot"]
    url: str | None = None
    selector: str | None = Field(default=None, max_length=500)
    secret_env: str | None = Field(default=None, pattern=r"^XBOW_BROWSER_SECRET_[A-Z0-9_]+$")
    timeout_ms: int = Field(default=10_000, ge=100, le=30_000)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.operation == "navigate" and not self.url:
            raise ValueError("navigate requires url")
        if self.operation in {"click", "wait_for", "fill"} and not self.selector:
            raise ValueError(f"{self.operation} requires selector")
        if self.operation == "fill" and not self.secret_env:
            raise ValueError("fill requires a XBOW_BROWSER_SECRET_* environment reference")
        if self.operation != "fill" and self.secret_env:
            raise ValueError("secret_env is only valid for fill")
        return self


class BrowserFlowInput(BaseModel):
    steps: list[BrowserStep] = Field(min_length=1, max_length=25)


@dataclass(frozen=True)
class BrowserExecutionResult:
    status: str
    observations: list[dict]
    screenshots: list[tuple[str, bytes]]


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _campaign(campaign_id: str):
    from .main import Campaign

    record = Storage().get_campaign_record(campaign_id)
    if not record:
        raise HTTPException(status_code=404, detail="Campaign not found")
    raw, version = record
    return Campaign.model_validate(raw), version


def _flow_dedupe_key(campaign_id: str, version: int, flow: BrowserFlowInput) -> str:
    encoded = json.dumps(flow.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]
    return f"browser:v{version}:{campaign_id}:{digest}"


def _allowed_url(campaign, candidate: str, base: str | None = None) -> str:
    from .main import is_host_allowed

    resolved = urljoin(base or str(campaign.target.primary_url), candidate)
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BrowserPolicyError("browser navigation requires explicit HTTP(S) URL")
    if parsed.username or parsed.password:
        raise BrowserPolicyError("userinfo in browser URLs is forbidden")
    if not is_host_allowed(parsed.hostname.lower().rstrip("."), campaign.target.rules.allowed_targets, campaign.target.rules.denied_targets):
        raise BrowserPolicyError("browser URL is outside declared scope")
    return resolved


def validate_flow(campaign, flow: BrowserFlowInput) -> BrowserFlowInput:
    base = str(campaign.target.primary_url)
    for step in flow.steps:
        if step.operation == "navigate":
            base = _allowed_url(campaign, step.url or "", base)
    return flow


@router.post("/api/campaigns/{campaign_id}/browser-flows")
def queue_browser_flow(campaign_id: str, flow: BrowserFlowInput):
    campaign, version = _campaign(campaign_id)
    validate_flow(campaign, flow)
    if campaign.state.value in {"cancelled", "completed"}:
        raise HTTPException(status_code=409, detail=f"Cannot queue browser flow from {campaign.state}")
    job = JobQueue().enqueue(
        campaign.id,
        "browser_flow",
        {"campaign_id": campaign.id, "steps": flow.model_dump(mode="json")["steps"]},
        max_attempts=2,
        dedupe_key=_flow_dedupe_key(campaign.id, version, flow),
    )
    campaign.events.append({"type": "browser_flow_queued", "job_id": job["id"], "at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
    try:
        Storage().save_campaign(campaign.model_dump(mode="json"), expected_version=version)
    except CampaignConflictError as exc:
        raise HTTPException(status_code=409, detail="Campaign changed concurrently; reload and retry") from exc
    return job


def execute_browser_flow(campaign, payload: dict) -> BrowserExecutionResult:
    flow = validate_flow(campaign, BrowserFlowInput.model_validate({"steps": payload.get("steps", [])}))
    if not _bool_env("XBOW_ENABLE_BROWSER_AUTOMATION", False):
        return BrowserExecutionResult(status="dry_run", observations=[{"steps": len(flow.steps)}], screenshots=[])

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPolicyError("Playwright is not installed") from exc

    observations: list[dict] = []
    screenshots: list[tuple[str, bytes]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = browser.new_context(ignore_https_errors=False)
        page = context.new_page()

        def route_guard(route):
            try:
                _allowed_url(campaign, route.request.url, page.url if page.url != "about:blank" else None)
            except BrowserPolicyError:
                route.abort("blockedbyclient")
            else:
                route.continue_()

        context.route("**/*", route_guard)
        try:
            for index, step in enumerate(flow.steps, 1):
                if step.operation == "navigate":
                    target = _allowed_url(campaign, step.url or "", page.url if page.url != "about:blank" else None)
                    response = page.goto(target, wait_until="domcontentloaded", timeout=step.timeout_ms)
                    final_url = _allowed_url(campaign, page.url, target)
                    observations.append({"step": index, "operation": "navigate", "url": final_url, "status": response.status if response else None})
                elif step.operation == "click":
                    page.locator(step.selector or "").click(timeout=step.timeout_ms)
                    if page.url != "about:blank":
                        _allowed_url(campaign, page.url)
                    observations.append({"step": index, "operation": "click", "selector": step.selector})
                elif step.operation == "fill":
                    secret = os.getenv(step.secret_env or "")
                    if secret is None:
                        raise BrowserPolicyError(f"required browser secret is unavailable: {step.secret_env}")
                    page.locator(step.selector or "").fill(secret, timeout=step.timeout_ms)
                    observations.append({"step": index, "operation": "fill", "selector": step.selector, "secret_env": step.secret_env})
                elif step.operation == "wait_for":
                    page.locator(step.selector or "").wait_for(state="visible", timeout=step.timeout_ms)
                    observations.append({"step": index, "operation": "wait_for", "selector": step.selector})
                elif step.operation == "screenshot":
                    data = page.screenshot(full_page=True)
                    screenshots.append((f"browser-step-{index}.png", data))
                    observations.append({"step": index, "operation": "screenshot", "bytes": len(data)})
        finally:
            context.close()
            browser.close()
    return BrowserExecutionResult(status="completed", observations=observations, screenshots=screenshots)


def persist_browser_result(
    store: Storage,
    campaign_id: str,
    result: BrowserExecutionResult,
    *,
    idempotency_prefix: str | None = None,
) -> list[dict]:
    artifacts = [
        store.put_artifact(
            campaign_id,
            "http_evidence",
            json.dumps({"status": result.status, "observations": result.observations}, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            media_type="application/json",
            idempotency_key=f"{idempotency_prefix}:browser:evidence" if idempotency_prefix else None,
        )
    ]
    for index, (_name, content) in enumerate(result.screenshots, 1):
        artifacts.append(
            store.put_artifact(
                campaign_id,
                "screenshot",
                content,
                media_type="image/png",
                idempotency_key=f"{idempotency_prefix}:browser:screenshot:{index}" if idempotency_prefix else None,
            )
        )
    return artifacts
