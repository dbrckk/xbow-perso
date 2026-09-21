from __future__ import annotations

from typing import Any


def build_value_efficiency_signal(
    *,
    status: str,
    opportunity_score: int,
    research_focus: list[str],
    runtime_ready_categories: list[str],
    runtime_partial_categories: list[str],
    gold_standard_safe_harbor: bool | None,
) -> dict[str, Any]:
    """Estimate researcher-time efficiency without treating history as expected payout."""
    effort = 1.0
    reasons: list[str] = []

    if status == "READY":
        reasons.append("exact_review_profile_reduces_setup")
    elif status == "REVIEW":
        effort += 1.0
        reasons.append("manual_review_cost")
    else:
        return {
            "value_efficiency_score": 0,
            "effort_factor": 99.0,
            "efficiency_reasons": ["program_blocked"],
            "advisory_only": True,
            "historical_signals_are_not_expected_payout": True,
            "automatic_launch": False,
            "scope_expansion": False,
        }

    focus = [str(item) for item in research_focus if str(item)]
    ready = set(str(item) for item in runtime_ready_categories)
    partial = set(str(item) for item in runtime_partial_categories)

    if focus:
        ready_count = sum(1 for item in focus if item in ready)
        partial_count = sum(1 for item in focus if item in partial)
        if ready_count == len(focus):
            reasons.append("runtime_matches_focus")
        elif ready_count:
            effort += 0.25
            reasons.append("runtime_partially_matches_focus")
        elif partial_count:
            effort += 0.5
            reasons.append("runtime_partial_only")
        else:
            effort += 0.75
            reasons.append("runtime_gap_for_focus")

    if gold_standard_safe_harbor is not True:
        effort += 0.25
        reasons.append("safe_harbor_requires_extra_review")

    score = max(0, min(100, int(round(float(opportunity_score) / effort))))
    return {
        "value_efficiency_score": score,
        "effort_factor": round(effort, 2),
        "efficiency_reasons": reasons,
        "advisory_only": True,
        "historical_signals_are_not_expected_payout": True,
        "automatic_launch": False,
        "scope_expansion": False,
    }


def select_diversified_portfolio(
    programs: list[dict[str, Any]],
    *,
    limit: int = 5,
    min_score: int = 50,
) -> list[dict[str, Any]]:
    """Select READY bounty programs with diversification and bounded exploration."""
    safe_limit = max(1, min(20, int(limit)))
    safe_min = max(0, min(100, int(min_score)))

    candidates = [
        dict(item)
        for item in programs
        if str(item.get("status") or "") == "READY"
        and item.get("offers_bounties") is True
        and int(item.get("value_efficiency_score") or 0) >= safe_min
    ]

    selected: list[dict[str, Any]] = []
    focus_counts: dict[str, int] = {}

    while candidates and len(selected) < safe_limit:
        ranked: list[tuple[int, int, str, dict[str, Any], str]] = []
        for item in candidates:
            focus = [str(value) for value in list(item.get("research_focus") or []) if str(value)]
            primary = focus[0] if focus else "other"
            concentration_penalty = min(30, 12 * focus_counts.get(primary, 0))
            adjusted = max(
                0,
                int(item.get("value_efficiency_score") or 0) - concentration_penalty,
            )
            ranked.append(
                (
                    adjusted,
                    int(item.get("opportunity_score") or 0),
                    str(item.get("handle") or ""),
                    item,
                    primary,
                )
            )

        ranked.sort(key=lambda value: (-value[0], -value[1], value[2]))
        adjusted, _, _, picked, primary = ranked[0]
        picked["portfolio_score"] = adjusted
        picked["portfolio_primary_focus"] = primary
        picked["portfolio_concentration_penalty"] = (
            int(picked.get("value_efficiency_score") or 0) - adjusted
        )
        selected.append(picked)
        focus_counts[primary] = focus_counts.get(primary, 0) + 1
        candidates = [
            item for item in candidates
            if str(item.get("handle") or "") != str(picked.get("handle") or "")
        ]

    if safe_limit >= 4 and selected:
        selected_handles = {str(item.get("handle") or "") for item in selected}
        exploration = [
            dict(item)
            for item in programs
            if str(item.get("status") or "") == "READY"
            and item.get("offers_bounties") is True
            and int(item.get("value_efficiency_score") or 0) >= safe_min
            and str(item.get("handle") or "") not in selected_handles
            and any(
                reason in {"new_program", "catalog_changed", "recent_catalog_change"}
                for reason in (
                    list(item.get("reasons") or [])
                    + list(item.get("opportunity_reasons") or [])
                )
            )
        ]
        exploration.sort(
            key=lambda item: (
                -int(item.get("opportunity_score") or 0),
                -int(item.get("value_efficiency_score") or 0),
                str(item.get("handle") or ""),
            )
        )
        if exploration:
            candidate = exploration[0]
            candidate["portfolio_score"] = int(candidate.get("value_efficiency_score") or 0)
            candidate["portfolio_primary_focus"] = str(
                (list(candidate.get("research_focus") or []) or ["other"])[0]
            )
            candidate["portfolio_concentration_penalty"] = 0
            candidate["portfolio_exploration_slot"] = True
            if len(selected) >= safe_limit:
                selected[-1] = candidate
            else:
                selected.append(candidate)

    return selected
