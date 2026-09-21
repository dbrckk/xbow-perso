from __future__ import annotations

import math
from typing import Any


_RUNTIME_REQUIREMENTS = {
    "access_control": ("browser",),
    "auth_session": ("browser",),
    "api_graphql": ("recon",),
    "business_logic": ("browser",),
    "xss_client": ("browser", "scanner"),
    "ssrf_oob": ("recon",),
    "injection_rce": ("scanner",),
    "cache_proxy": ("recon",),
    "cloud_surface": ("recon",),
    "file_path": ("browser", "scanner"),
    "information_disclosure": ("recon",),
    "ai_llm": ("browser",),
    "other": ("recon",),
}


def build_opportunity_signal(
    *,
    status: str,
    program: dict[str, Any],
    signal: dict[str, Any],
    runtime: dict[str, Any],
    is_new: bool,
    is_changed: bool,
) -> dict[str, Any]:
    """Explainable advisory ranking for researcher time allocation.

    Uses only public historical metadata, current program catalog state, current
    runtime readiness and prior explicit review state. It never authorizes a
    target or enables an execution capability.
    """
    reasons: list[str] = []
    score = 0

    if status == "READY":
        score += 25
        reasons.append("ready_exact_review_profile")
    elif status == "REVIEW":
        score += 8
        reasons.append("review_required")
    else:
        reasons.append("program_blocked")

    if program.get("offers_bounties") is True:
        score += 20
        reasons.append("bounty_program")
    if program.get("gold_standard_safe_harbor") is True:
        score += 5
        reasons.append("gold_standard_safe_harbor")

    if is_new:
        score += 15
        reasons.append("new_program")
    elif is_changed:
        score += 10
        reasons.append("recent_catalog_change")

    historical_value = max(0.0, float(signal.get("historical_value_score") or 0.0))
    value_bonus = min(15, int(round(historical_value)))
    if value_bonus:
        score += value_bonus
        reasons.append("public_historical_value_signal")

    high_critical = max(0, int(signal.get("high_critical_count") or 0))
    disclosed_count = max(0, int(signal.get("disclosed_report_count") or 0))
    severity_density = (
        min(1.0, high_critical / disclosed_count) if disclosed_count else 0.0
    )
    severity_bonus = int(round(severity_density * 10))
    if severity_bonus:
        score += severity_bonus
        reasons.append("high_critical_public_density")

    usd_max = max(0.0, float(signal.get("usd_awarded_max") or 0.0))
    award_signal = min(10, int(math.log10(1.0 + usd_max) * 2)) if usd_max else 0
    if award_signal:
        score += award_signal
        reasons.append("documented_public_usd_award")

    categories = [str(item) for item in list(signal.get("top_categories") or [])[:4]]
    runtime_ready_categories: list[str] = []
    runtime_partial_categories: list[str] = []
    for category in categories:
        requirements = _RUNTIME_REQUIREMENTS.get(category, ("recon",))
        ready_count = sum(1 for name in requirements if bool(runtime.get(name)))
        if ready_count == len(requirements):
            runtime_ready_categories.append(category)
        elif ready_count:
            runtime_partial_categories.append(category)

    if runtime_ready_categories:
        score += min(10, 4 + (2 * len(runtime_ready_categories)))
        reasons.append("runtime_matches_public_categories")
    elif runtime_partial_categories:
        score += 2
        reasons.append("runtime_partially_matches_public_categories")

    if status == "BLOCKED":
        score = 0

    return {
        "opportunity_score": min(100, score),
        "research_focus": runtime_ready_categories[:3] or categories[:3],
        "runtime_ready_categories": runtime_ready_categories,
        "runtime_partial_categories": runtime_partial_categories,
        "public_high_critical_density": round(severity_density, 3),
        "documented_public_usd_max": usd_max,
        "reasons": reasons,
        "advisory_only": True,
        "historical_signals_are_not_expected_payout": True,
        "automatic_launch": False,
        "scope_expansion": False,
    }
