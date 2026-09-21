from __future__ import annotations

from itertools import combinations
from typing import Any

# Advisory-only composition rules learned from recurring public bug-bounty patterns.
# They never authorize a target, execute a request, or raise scanner permissions.
_CHAIN_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "ssrf-disclosure-cloud",
        "requires": ("ssrf_oob", "information_disclosure", "cloud_surface"),
        "label": "Server-side reachability + internal context + cloud surface",
        "weight": 1.35,
    },
    {
        "id": "auth-access-api",
        "requires": ("auth_session", "access_control", "api_graphql"),
        "label": "Authentication state + authorization boundary + API surface",
        "weight": 1.30,
    },
    {
        "id": "workflow-race-access",
        "requires": ("business_logic", "access_control"),
        "label": "Workflow invariant + authorization boundary",
        "weight": 1.25,
    },
    {
        "id": "ai-agent-access",
        "requires": ("ai_llm", "access_control", "api_graphql"),
        "label": "AI input boundary + consequential tool/data access",
        "weight": 1.35,
    },
    {
        "id": "file-disclosure-access",
        "requires": ("file_path", "information_disclosure", "access_control"),
        "label": "File boundary + sensitive data + authorization boundary",
        "weight": 1.20,
    },
    {
        "id": "cache-auth",
        "requires": ("cache_proxy", "auth_session"),
        "label": "Proxy/cache behavior + authenticated state",
        "weight": 1.15,
    },
)


def build_chain_intelligence(categories: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank plausible vulnerability compositions without performing exploitation."""
    by_name = {
        str(item.get("category")): item
        for item in categories
        if isinstance(item, dict) and item.get("category")
    }
    candidates: list[dict[str, Any]] = []
    for rule in _CHAIN_RULES:
        present = [name for name in rule["requires"] if name in by_name]
        if len(present) < 2:
            continue
        evidence = sum(float(by_name[name].get("evidence_score") or 0) for name in present)
        high_critical = sum(int(by_name[name].get("high_critical_count") or 0) for name in present)
        usd_max = max(float(by_name[name].get("usd_awarded_max") or 0) for name in present)
        completeness = len(present) / len(rule["requires"])
        score = round((evidence + 2 * high_critical) * completeness * float(rule["weight"]), 3)
        candidates.append(
            {
                "chain_id": rule["id"],
                "label": rule["label"],
                "required_categories": list(rule["requires"]),
                "observed_categories": present,
                "missing_categories": [name for name in rule["requires"] if name not in by_name],
                "completeness": round(completeness, 3),
                "evidence_score": score,
                "historical_usd_award_max": round(usd_max, 2),
                "advisory_only": True,
                "automatic_execution": False,
            }
        )

    # Also surface strong two-family compositions not covered by a named rule.
    strongest = sorted(
        by_name.items(),
        key=lambda item: float(item[1].get("evidence_score") or 0),
        reverse=True,
    )[:6]
    covered_pairs = {
        frozenset(pair)
        for rule in _CHAIN_RULES
        for pair in combinations(rule["requires"], 2)
    }
    for (left, a), (right, b) in combinations(strongest, 2):
        if frozenset((left, right)) in covered_pairs:
            continue
        score = round(
            (float(a.get("evidence_score") or 0) + float(b.get("evidence_score") or 0)) * 0.45,
            3,
        )
        candidates.append(
            {
                "chain_id": f"emergent:{left}+{right}",
                "label": "Emergent public-evidence composition",
                "required_categories": [left, right],
                "observed_categories": [left, right],
                "missing_categories": [],
                "completeness": 1.0,
                "evidence_score": score,
                "historical_usd_award_max": round(
                    max(float(a.get("usd_awarded_max") or 0), float(b.get("usd_awarded_max") or 0)),
                    2,
                ),
                "advisory_only": True,
                "automatic_execution": False,
            }
        )

    candidates.sort(
        key=lambda item: (
            -float(item["evidence_score"]),
            -float(item["completeness"]),
            str(item["chain_id"]),
        )
    )
    return {
        "mode": "public-evidence-chain-analysis",
        "candidates": candidates[:20],
        "limitations": [
            "A candidate chain is a hypothesis, not a confirmed vulnerability.",
            "Historical public evidence never expands an authorized campaign scope.",
            "No request, exploit, credential use, or scanner enablement is performed here.",
            "Human review and reproducible in-scope evidence remain required before reporting.",
        ],
        "automatic_execution": False,
    }
