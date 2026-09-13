from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .main import Campaign, is_host_allowed


_CREATE_FLOW_MUTATION = """
mutation CreateFlow($provider: String!, $input: String!) {
  createFlow(modelProvider: $provider, input: $input) {
    id
    title
    status
  }
}
""".strip()

_PROVIDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


class PentagiPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiFlowPlan:
    endpoint: str
    payload: dict[str, object]
    target: str
    model_provider: str
    dry_run: bool = True
    execution_supported: bool = False


def _configured_base_url() -> str:
    value = (os.getenv("XBOW_PENTAGI_BASE_URL") or "").strip()
    if not value:
        raise PentagiPolicyError("XBOW_PENTAGI_BASE_URL is required")
    return value


def _configured_provider() -> str:
    value = (os.getenv("XBOW_PENTAGI_MODEL_PROVIDER") or "").strip()
    if not value:
        raise PentagiPolicyError("XBOW_PENTAGI_MODEL_PROVIDER is required")
    if not _PROVIDER_RE.fullmatch(value):
        raise PentagiPolicyError("XBOW_PENTAGI_MODEL_PROVIDER is invalid")
    return value


def _graphql_endpoint(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme.lower() != "https":
        raise PentagiPolicyError("PentAGI endpoint must use HTTPS")
    if not parsed.hostname:
        raise PentagiPolicyError("PentAGI endpoint has no hostname")
    if parsed.username or parsed.password:
        raise PentagiPolicyError("PentAGI endpoint must not contain credentials")
    if parsed.query or parsed.fragment:
        raise PentagiPolicyError("PentAGI endpoint must not contain query or fragment")
    if parsed.path not in {"", "/"}:
        raise PentagiPolicyError("PentAGI base URL must not contain a path")
    return base_url.rstrip("/") + "/api/v1/graphql"


def _safe_campaign_target(campaign: Campaign) -> str:
    target = str(campaign.target.primary_url)
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    rules = campaign.target.rules

    if not host or not is_host_allowed(
        host,
        rules.allowed_targets,
        rules.denied_targets,
    ):
        raise PentagiPolicyError("Target is outside declared scope")
    if not rules.automated_scanning:
        raise PentagiPolicyError("Automated scanning is disabled by program rules")
    if (
        rules.destructive_testing
        or rules.denial_of_service
        or rules.social_engineering
        or rules.credential_attacks
    ):
        raise PentagiPolicyError(
            "Unsafe campaign flags cannot be delegated to PentAGI"
        )
    return target


def _flow_input(campaign: Campaign, target: str) -> str:
    rules = campaign.target.rules
    allowed = ", ".join(sorted(str(item) for item in rules.allowed_targets))
    denied = ", ".join(sorted(str(item) for item in rules.denied_targets)) or "(none)"
    return (
        "Authorized security assessment only. "
        f"Primary target: {target}. "
        f"Allowed targets: {allowed}. "
        f"Denied targets: {denied}. "
        f"Maximum request rate: {rules.max_requests_per_second:g} requests/second. "
        "Stay strictly inside the declared target scope. "
        "Do not perform denial-of-service, destructive testing, social engineering, "
        "or credential attacks. Stop rather than expanding scope when uncertain."
    )


def build_pentagi_flow_plan(
    campaign: Campaign,
    *,
    base_url: str | None = None,
    model_provider: str | None = None,
) -> PentagiFlowPlan:
    """Build a non-executing PentAGI request plan.

    This first adapter stage intentionally cannot submit a PentAGI flow. It creates
    a deterministic, scope-constrained GraphQL request only after the same campaign
    safety invariants used by active scanner workers have been satisfied.
    """

    target = _safe_campaign_target(campaign)
    configured_base = base_url if base_url is not None else _configured_base_url()
    endpoint = _graphql_endpoint(configured_base.strip())

    provider = (
        model_provider.strip()
        if model_provider is not None
        else _configured_provider()
    )
    if not _PROVIDER_RE.fullmatch(provider):
        raise PentagiPolicyError("PentAGI model provider is invalid")

    payload: dict[str, object] = {
        "query": _CREATE_FLOW_MUTATION,
        "variables": {
            "provider": provider,
            "input": _flow_input(campaign, target),
        },
    }
    return PentagiFlowPlan(
        endpoint=endpoint,
        payload=payload,
        target=target,
        model_provider=provider,
    )
