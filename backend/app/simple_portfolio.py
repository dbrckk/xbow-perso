from __future__ import annotations

from typing import Any


def select_simple_six(programs: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick 2 easy + 2 medium + 2 high-value bounty candidates.

    READY programs are preferred. REVIEW programs may be proposed for the one-time
    human review flow, but they remain non-launchable until an exact reviewed
    profile is persisted for the current HackerOne snapshot.
    """
    pool = [
        dict(item)
        for item in programs
        if str(item.get("status") or "") in {"READY", "REVIEW"}
        and item.get("offers_bounties") is True
        and item.get("gold_standard_safe_harbor") is True
    ]

    def efficiency(item: dict[str, Any]) -> tuple[float, float, str]:
        return (
            -float(item.get("value_efficiency_score") or 0),
            float(item.get("effort_factor") or 99),
            str(item.get("handle") or ""),
        )

    easy_pool = sorted(
        pool,
        key=lambda item: (
            float(item.get("effort_factor") or 99),
            -float(item.get("value_efficiency_score") or 0),
            -float(item.get("opportunity_score") or 0),
            str(item.get("handle") or ""),
        ),
    )
    easy = easy_pool[:2]
    used = {str(item.get("handle") or "") for item in easy}

    remaining = [item for item in pool if str(item.get("handle") or "") not in used]
    if remaining:
        efforts = sorted(float(item.get("effort_factor") or 0) for item in remaining)
        median = efforts[len(efforts) // 2]
        medium_pool = sorted(
            remaining,
            key=lambda item: (
                abs(float(item.get("effort_factor") or 0) - median),
                *efficiency(item),
            ),
        )
    else:
        medium_pool = []
    medium = medium_pool[:2]
    used.update(str(item.get("handle") or "") for item in medium)

    remaining = [item for item in pool if str(item.get("handle") or "") not in used]
    high_value = sorted(
        remaining,
        key=lambda item: (
            -float(item.get("historical_usd_awarded_max") or 0),
            -float(item.get("historical_value_score") or 0),
            -float(item.get("opportunity_score") or 0),
            str(item.get("handle") or ""),
        ),
    )[:2]

    groups = {"easy": easy, "medium": medium, "high_value": high_value}
    selected = easy + medium + high_value
    ready_count = sum(
        1 for item in selected if str(item.get("status") or "") == "READY"
    )
    review_count = sum(
        1 for item in selected if str(item.get("status") or "") == "REVIEW"
    )
    complete = len(easy) == 2 and len(medium) == 2 and len(high_value) == 2
    return {
        "groups": groups,
        "selection": selected,
        "handles": [str(item.get("handle") or "") for item in selected],
        "complete": complete,
        "selection_count": len(selected),
        "ready_count": ready_count,
        "review_count": review_count,
        "launch_ready": complete and review_count == 0,
        "selection_policy": {
            "easy": "lowest effort bounty candidates, preferring reviewed READY profiles",
            "medium": "candidates around the remaining median effort, then best efficiency",
            "high_value": "remaining candidates with the strongest public historical award signal",
        },
        "historical_value_is_advisory_only": True,
        "scope_expansion": False,
    }
