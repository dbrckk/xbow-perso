from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from .main import Campaign
from .pentagi_adapter import build_pentagi_flow_plan
from .pentagi_broker_auth import (
    PentagiBrokerAuthError,
    load_pentagi_broker_auth,
)


_NATIVE_FUNCTIONS = (
    "terminal",
    "file",
    "browser",
    "search_in_memory",
    "search_guide",
    "search_answer",
    "search_code",
    "store_guide",
    "store_answer",
    "store_code",
    "google",
    "duckduckgo",
    "tavily",
    "firecrawl",
    "traversaal",
    "perplexity",
    "searxng",
    "sploitus",
    "graphiti_search",
)


class PentagiRestrictedPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiRestrictedRestPlan:
    endpoint: str
    payload: dict[str, object]
    target: str
    model_provider: str
    dry_run: bool = True
    execution_supported: bool = False


def _rest_flows_endpoint(graphql_endpoint: str) -> str:
    try:
        parsed = urlparse(graphql_endpoint)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError as exc:
        raise PentagiRestrictedPlanError("PentAGI endpoint is invalid") from exc

    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or username
        or password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/api/v1/graphql"
    ):
        raise PentagiRestrictedPlanError(
            "PentAGI GraphQL endpoint cannot be converted to restricted REST endpoint"
        )

    authority = hostname
    if ":" in hostname and not hostname.startswith("["):
        authority = f"[{hostname}]"
    if port is not None:
        if not 1 <= port <= 65535:
            raise PentagiRestrictedPlanError("PentAGI endpoint port is invalid")
        authority = f"{authority}:{port}"
    return f"https://{authority}/api/v1/flows/"


def _broker_url() -> str:
    value = (os.getenv("XBOW_PENTAGI_BROKER_URL") or "").strip()
    if not value:
        raise PentagiRestrictedPlanError("XBOW_PENTAGI_BROKER_URL is required")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError as exc:
        raise PentagiRestrictedPlanError("XBOW_PENTAGI_BROKER_URL is invalid") from exc
    if parsed.scheme.lower() != "https" or not hostname:
        raise PentagiRestrictedPlanError("PentAGI broker URL must use HTTPS")
    if username or password:
        raise PentagiRestrictedPlanError("PentAGI broker URL must not contain credentials")
    if port is not None and not 1 <= port <= 65535:
        raise PentagiRestrictedPlanError("PentAGI broker URL port is invalid")
    if parsed.fragment:
        raise PentagiRestrictedPlanError("PentAGI broker URL must not contain a fragment")
    return value


def _broker_token() -> str:
    try:
        return load_pentagi_broker_auth().token
    except PentagiBrokerAuthError as exc:
        raise PentagiRestrictedPlanError(
            "PentAGI broker token is unavailable"
        ) from exc


def _broker_schema() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "xbow_http_request",
            "description": (
                "Perform one scope-checked and rate-limited HTTP request through "
                "the XBOW authorization broker."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "HEAD"],
                    },
                    "url": {
                        "type": "string",
                        "description": "Absolute HTTP(S) URL; XBOW validates scope before sending.",
                    },
                },
                "required": ["method", "url"],
                "additionalProperties": False,
            },
        },
    }


def build_restricted_pentagi_rest_plan(
    campaign: Campaign,
) -> PentagiRestrictedRestPlan:
    """Build a non-executable PentAGI REST plan with native tools disabled.

    The plan remains execution_supported=False until the XBOW broker itself exists
    and is independently verified to enforce campaign scope and request rate.
    """

    base = build_pentagi_flow_plan(campaign)
    variables = base.payload.get("variables")
    if not isinstance(variables, dict):
        raise PentagiRestrictedPlanError("PentAGI base plan variables are invalid")
    input_text = variables.get("input")
    if not isinstance(input_text, str) or not input_text:
        raise PentagiRestrictedPlanError("PentAGI base plan input is invalid")

    payload: dict[str, object] = {
        "input": input_text,
        "provider": base.model_provider,
        "functions": {
            "token": _broker_token(),
            "disabled": [{"name": name} for name in _NATIVE_FUNCTIONS],
            "functions": [
                {
                    "name": "xbow_http_request",
                    "url": _broker_url(),
                    "timeout": 30,
                    "schema": _broker_schema(),
                }
            ],
        },
    }

    return PentagiRestrictedRestPlan(
        endpoint=_rest_flows_endpoint(base.endpoint),
        payload=payload,
        target=base.target,
        model_provider=base.model_provider,
    )
