from __future__ import annotations

from typing import Any

from .chain_intelligence import build_chain_intelligence
from .observation_graph import ObservationGraph, PlannedAction


_FAMILY_TO_CATEGORY = {
    "alternate-representation-access-control": "access_control",
    "graphql-authorization": "api_graphql",
    "graphql-data-segregation": "api_graphql",
    "authentication-state-machine": "auth_session",
    "transaction-reconciliation-invariants": "business_logic",
    "server-side-fetch-boundaries": "ssrf_oob",
}


def _observed_categories(
    graph: ObservationGraph,
    high_value_intelligence: dict[str, Any],
) -> set[str]:
    observed: set[str] = set()
    for focus in high_value_intelligence.get("focuses") or []:
        family = str(focus.get("family") or "")
        if int(focus.get("score") or 0) >= 50 and family in _FAMILY_TO_CATEGORY:
            observed.add(_FAMILY_TO_CATEGORY[family])

    joined = "\n".join(str(item.value).lower() for item in graph.values())
    signal_map = {
        "api_graphql": ("graphql", "/graphql", "openapi", "swagger"),
        "auth_session": ("login", "oauth", "mfa", "2fa", "session", "jwt"),
        "business_logic": ("payment", "withdraw", "transfer", "refund", "checkout"),
        "ssrf_oob": ("webhook", "callback", "preview", "import", "url="),
        "ai_llm": ("llm", "prompt", "assistant", "agent", "rag"),
        "file_path": ("upload", "download", "attachment", "file"),
        "cloud_surface": ("s3", "bucket", "cloudfront", "storage"),
        "information_disclosure": ("source map", ".map", "debug", "stack trace"),
    }
    for category, signals in signal_map.items():
        if any(signal in joined for signal in signals):
            observed.add(category)
    return observed


def build_campaign_chain_context(
    graph: ObservationGraph,
    high_value_intelligence: dict[str, Any],
) -> dict[str, Any]:
    observed = _observed_categories(graph, high_value_intelligence)
    # Chain scoring consumes campaign observations only. Historical award/category
    # data is not treated as target evidence.
    categories = [
        {
            "category": name,
            "evidence_score": 10.0,
            "high_critical_count": 0,
            "usd_awarded_max": 0.0,
        }
        for name in sorted(observed)
    ]
    chain = build_chain_intelligence(categories)
    candidates = [
        item for item in chain["candidates"]
        if len(item.get("observed_categories") or []) >= 2
    ]
    return {
        "observed_categories": sorted(observed),
        "candidates": candidates[:8],
        "advisory_only": True,
        "historical_award_used_as_target_evidence": False,
        "automatic_execution": False,
    }


def prioritize_with_chain_context(
    action: PlannedAction,
    context: dict[str, Any],
) -> tuple[PlannedAction, dict[str, Any]]:
    candidates = list(context.get("candidates") or [])
    complete = [item for item in candidates if float(item.get("completeness") or 0) >= 1.0]
    selected = complete[:3] if complete else candidates[:2]
    result = {
        "applied": False,
        "chain_ids": [str(item.get("chain_id")) for item in selected],
        "advisory_only": True,
        "action_kind_changed": False,
        "target_changed": False,
        "automatic_execution": False,
        "scope_expansion": False,
    }
    if action.kind not in {"crawl", "scan", "validate"} or not selected:
        return action, result

    boost = 4 if complete else 2
    priority = min(99, max(action.priority, min(99, action.priority + boost)))
    chain_ids = ", ".join(result["chain_ids"])
    result["applied"] = True
    return PlannedAction(
        action.kind,
        action.target,
        f"{action.reason}; observed chain candidates: {chain_ids}",
        priority,
    ), result
