from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .api_outbox import has_event, pending_request_id
from .campaign_audit import append_campaign_event
from .queue_backend import QueueBackend, create_queue
from .secret_vault import SecretVaultError, get_secret, vault_enabled
from .storage import CampaignConflictError
from .storage_backend import StorageBackend, create_storage
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
    identity_label: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9._ -]+$",
    )
    storage_state_secret_env: str | None = Field(
        default=None,
        pattern=r"^XBOW_BROWSER_SECRET_[A-Z0-9_]+$",
    )


@dataclass(frozen=True)
class BrowserExecutionResult:
    status: str
    observations: list[dict]
    screenshots: list[tuple[str, bytes]]
    identity_label: str | None = None


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


def _browser_secret(secret_env: str) -> str:
    try:
        use_vault = vault_enabled()
    except SecretVaultError as exc:
        raise BrowserPolicyError("browser vault configuration is invalid") from exc

    if use_vault:
        if os.getenv(secret_env):
            raise BrowserPolicyError(
                f"vault enabled but legacy {secret_env} fallback is forbidden"
            )
        vault_name = "browser." + secret_env.removeprefix("XBOW_BROWSER_SECRET_").lower()
        try:
            return get_secret(vault_name)
        except SecretVaultError as exc:
            raise BrowserPolicyError(
                f"required browser secret is unavailable: {secret_env}"
            ) from exc

    secret = os.getenv(secret_env)
    if secret is None:
        raise BrowserPolicyError(f"required browser secret is unavailable: {secret_env}")
    return secret


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _campaign(campaign_id: str, store: StorageBackend | None = None):
    from .main import Campaign

    backend = store or create_storage()
    record = backend.get_campaign_record(campaign_id)
    if not record:
        raise HTTPException(status_code=404, detail="Campaign not found")
    raw, version = record
    return Campaign.model_validate(raw), version


def _flow_fingerprint(flow: BrowserFlowInput) -> str:
    encoded = json.dumps(
        flow.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _flow_dedupe_key(campaign_id: str, version: int, flow: BrowserFlowInput) -> str:
    """Backward-compatible deterministic key helper for historical callers/tests."""
    digest = _flow_fingerprint(flow)[:24]
    return f"browser:v{version}:{campaign_id}:{digest}"


def _save_campaign(store: StorageBackend, campaign, version: int) -> int:
    try:
        return store.save_campaign(
            campaign.model_dump(mode="json"),
            expected_version=version,
        )
    except CampaignConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Campaign changed concurrently; reload and retry",
        ) from exc


def _reconcile_browser_flow_queued(
    store: StorageBackend,
    campaign_id: str,
    job: dict,
    *,
    request_id: str,
    flow_fingerprint: str,
    attempts: int = 3,
) -> None:
    for _ in range(attempts):
        campaign, version = _campaign(campaign_id, store)
        if has_event(
            campaign.events,
            "browser_flow_queued",
            identity={
                "request_id": request_id,
                "flow_fingerprint": flow_fingerprint,
                "job_id": job["id"],
            },
        ):
            return
        append_campaign_event(
            campaign.events,
            {
                "type": "browser_flow_queued",
                "request_id": request_id,
                "flow_fingerprint": flow_fingerprint,
                "job_id": job["id"],
                "at": _utcnow(),
            },
        )
        campaign.updated_at = _utcnow()
        try:
            store.save_campaign(
                campaign.model_dump(mode="json"),
                expected_version=version,
            )
            return
        except CampaignConflictError:
            continue
    raise HTTPException(
        status_code=409,
        detail="Browser job queued but campaign audit reconciliation conflicted; retry safely",
    )


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


def _browser_storage_state(campaign, secret_env: str | None) -> dict | None:
    """Load a Playwright storage-state secret and reject any out-of-scope state."""
    if not secret_env:
        return None

    raw = _browser_secret(secret_env)
    encoded = raw.encode("utf-8")
    if len(encoded) > 131_072:
        raise BrowserPolicyError("browser storage state exceeds 128 KiB")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BrowserPolicyError("browser storage state must be valid JSON") from exc
    if not isinstance(document, dict):
        raise BrowserPolicyError("browser storage state must be a JSON object")

    cookies = document.get("cookies", [])
    origins = document.get("origins", [])
    if not isinstance(cookies, list) or len(cookies) > 100:
        raise BrowserPolicyError("browser storage state cookies must be a list of at most 100")
    if not isinstance(origins, list) or len(origins) > 30:
        raise BrowserPolicyError("browser storage state origins must be a list of at most 30")

    from .main import is_host_allowed

    rules = campaign.target.rules
    primary_host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower().rstrip(".")

    for cookie in cookies:
        if not isinstance(cookie, dict):
            raise BrowserPolicyError("browser storage state cookie is invalid")
        domain = str(cookie.get("domain") or "").lower().lstrip(".").rstrip(".")
        name = cookie.get("name")
        value = cookie.get("value")
        if not domain or not isinstance(name, str) or not isinstance(value, str):
            raise BrowserPolicyError("browser storage state cookie fields are invalid")
        domain_covers_primary = bool(
            primary_host
            and (primary_host == domain or primary_host.endswith(f".{domain}"))
            and is_host_allowed(
                primary_host,
                rules.allowed_targets,
                rules.denied_targets,
            )
        )
        if not domain_covers_primary and not is_host_allowed(
            domain,
            rules.allowed_targets,
            rules.denied_targets,
        ):
            raise BrowserPolicyError("browser storage state contains an out-of-scope cookie domain")

    for origin in origins:
        if not isinstance(origin, dict):
            raise BrowserPolicyError("browser storage state origin is invalid")
        origin_url = str(origin.get("origin") or "")
        _allowed_url(campaign, origin_url)
        local_storage = origin.get("localStorage", [])
        if not isinstance(local_storage, list) or len(local_storage) > 200:
            raise BrowserPolicyError(
                "browser storage state localStorage must be a list of at most 200 entries"
            )

    return {"cookies": cookies, "origins": origins}


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
    store = create_storage()
    jobs: QueueBackend = create_queue()
    campaign, version = _campaign(campaign_id, store)
    validate_flow(campaign, flow)
    if campaign.state.value in {"cancelled", "completed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot queue browser flow from {campaign.state}",
        )

    flow_fingerprint = _flow_fingerprint(flow)
    request_id = pending_request_id(
        campaign.events,
        requested_type="browser_flow_requested",
        completed_type="browser_flow_queued",
        identity={"flow_fingerprint": flow_fingerprint},
    ) or str(uuid4())

    if not has_event(
        campaign.events,
        "browser_flow_requested",
        identity={
            "request_id": request_id,
            "flow_fingerprint": flow_fingerprint,
        },
    ):
        append_campaign_event(
            campaign.events,
            {
                "type": "browser_flow_requested",
                "request_id": request_id,
                "flow_fingerprint": flow_fingerprint,
                "at": _utcnow(),
            },
        )
        campaign.updated_at = _utcnow()
        _save_campaign(store, campaign, version)

    latest, _latest_version = _campaign(campaign.id, store)
    validate_flow(latest, flow)
    if latest.state.value in {"cancelled", "completed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot queue browser flow from {latest.state}",
        )

    job = jobs.enqueue(
        latest.id,
        "browser_flow",
        {
            "campaign_id": latest.id,
            **flow.model_dump(mode="json", exclude_none=True),
        },
        max_attempts=2,
        dedupe_key=f"browser:{request_id}",
    )
    _reconcile_browser_flow_queued(
        store,
        latest.id,
        job,
        request_id=request_id,
        flow_fingerprint=flow_fingerprint,
    )
    return job


def execute_browser_flow(campaign, payload: dict) -> BrowserExecutionResult:
    flow = validate_flow(campaign, BrowserFlowInput.model_validate(payload))
    if not _bool_env("XBOW_ENABLE_BROWSER_AUTOMATION", False):
        preview = {"steps": len(flow.steps)}
        if flow.identity_label:
            preview["identity_label"] = flow.identity_label
        return BrowserExecutionResult(
            status="dry_run",
            observations=[preview],
            screenshots=[],
            identity_label=flow.identity_label,
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserPolicyError("Playwright is not installed") from exc

    observations: list[dict] = []
    screenshots: list[tuple[str, bytes]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        storage_state = _browser_storage_state(campaign, flow.storage_state_secret_env)
        context_options = {"ignore_https_errors": False}
        if storage_state is not None:
            context_options["storage_state"] = storage_state
        context = browser.new_context(**context_options)
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
                    rendered = page.content().encode("utf-8", errors="replace")
                    navigation = {
                        "step": index,
                        "operation": "navigate",
                        "url": final_url,
                        "status": response.status if response else None,
                        "content_sha256": hashlib.sha256(rendered).hexdigest(),
                        "content_bytes": len(rendered),
                    }
                    if flow.identity_label:
                        navigation["identity_label"] = flow.identity_label
                    observations.append(navigation)

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
                    secret = _browser_secret(step.secret_env or "")
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
    return BrowserExecutionResult(
        status="completed",
        observations=observations,
        screenshots=screenshots,
        identity_label=flow.identity_label,
    )


def persist_browser_result(
    store: StorageBackend,
    campaign_id: str,
    result: BrowserExecutionResult,
    *,
    idempotency_prefix: str | None = None,
) -> list[dict]:
    artifacts = [
        store.put_artifact(
            campaign_id,
            "http_evidence",
            json.dumps(
                {
                    "status": result.status,
                    "identity_label": result.identity_label,
                    "observations": result.observations,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8"),
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
