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
from .submission_api import router as submission_router

router = APIRouter()
router.routes.extend(submission_router.routes)


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
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise BrowserPolicyError(f"{name} must be a boolean")


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


def _assert_read_only_browser_method(method: str) -> None:
    normalized = method.strip().upper()
    if normalized not in {"GET", "HEAD", "OPTIONS"}:
        raise BrowserPolicyError("browser request method is not allowed in read-only mode")


def _assert_browser_policy(campaign) -> None:
    rules = campaign.target.rules
    if not rules.automated_scanning:
        raise BrowserPolicyError("browser automation is disabled by program rules")
    if (
        rules.destructive_testing
        or rules.denial_of_service
        or rules.social_engineering
        or rules.credential_attacks
    ):
        raise BrowserPolicyError(
            "unsafe campaign flags cannot be delegated to browser automation"
        )


def validate_flow(campaign, flow: BrowserFlowInput) -> BrowserFlowInput:
    _assert_browser_policy(campaign)
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
                _allowed_url(
                    campaign,
                    route.request.url,
                    page.url if page.url != "about:blank" else None,
                )
                _assert_read_only_browser_method(route.request.method)
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

                    links = []
                    for href in page.locator("a[href]").evaluate_all(
                        "(els) => els.map((el) => el.href)"
                    ):
                        try:
                            safe = _allowed_url(campaign, str(href), final_url)
                        except BrowserPolicyError:
                            continue
                        if safe not in links:
                            links.append(safe)
                        if len(links) >= 100:
                            break
                    if links:
                        observations.append(
                            {
                                "step": index,
                                "operation": "surface_links",
                                "urls": links,
                            }
                        )

                    forms = []
                    raw_forms = page.locator("form").evaluate_all(
                        """(forms) => forms.map((form) => ({
                          action: form.action || window.location.href,
                          method: (form.method || 'GET').toUpperCase(),
                          input_names: Array.from(
                            form.querySelectorAll('input[name], textarea[name], select[name]')
                          ).map((el) => el.name).filter(Boolean)
                        }))"""
                    )
                    for raw_form in raw_forms:
                        method = str(raw_form.get("method") or "GET").upper()
                        if method not in {"GET", "HEAD"}:
                            continue
                        try:
                            action_url = _allowed_url(
                                campaign,
                                str(raw_form.get("action") or final_url),
                                final_url,
                            )
                        except BrowserPolicyError:
                            continue
                        forms.append(
                            {
                                "action": action_url,
                                "method": method,
                                "input_names": sorted(
                                    {
                                        str(name).strip()
                                        for name in raw_form.get("input_names", [])
                                        if str(name).strip()
                                    }
                                )[:100],
                            }
                        )
                        if len(forms) >= 50:
                            break
                    if forms:
                        observations.append(
                            {
                                "step": index,
                                "operation": "surface_forms",
                                "forms": forms,
                            }
                        )

                    technologies = []
                    generator = page.locator('meta[name="generator"]').get_attribute("content")
                    if generator:
                        technologies.append(f"generator:{generator}"[:200])
                    framework_markers = page.evaluate(
                        """() => ({
                          next: Boolean(document.querySelector('#__NEXT_DATA__')),
                          nuxt: Boolean(window.__NUXT__),
                          react: Boolean(document.querySelector('[data-reactroot], [data-reactid]')),
                          angular: Boolean(document.querySelector('[ng-version]'))
                        })"""
                    )
                    for name, present in sorted(framework_markers.items()):
                        if present:
                            technologies.append(name)
                    if technologies:
                        observations.append(
                            {
                                "step": index,
                                "operation": "surface_technologies",
                                "technologies": sorted(set(technologies))[:20],
                            }
                        )
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
