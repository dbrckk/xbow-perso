from __future__ import annotations

from typing import Any

from .observation_graph import PlannedAction


def prioritize_action_with_intelligence(
    action: PlannedAction,
    high_value_intelligence: dict[str, Any],
) -> tuple[PlannedAction, dict[str, Any]]:
    """Attach advisory public-case focus to an already-safe planner transition.

    This function deliberately cannot change the action kind, target, scope,
    request budget, scanner selection, or policy gate. It only raises the
    presentation priority of crawl/scan/validate actions and records why.
    """
    focuses = list(high_value_intelligence.get("focuses") or [])
    matched = [item for item in focuses if int(item.get("score") or 0) >= 50]
    matched.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("family") or "")))
    selected = matched[:3]

    context = {
        "applied": False,
        "families": [str(item.get("family")) for item in selected],
        "public_case_ids": sorted(
            {
                str(case_id)
                for item in selected
                for case_id in (item.get("matched_case_ids") or [])
            }
        ),
        "observation_goals": sorted(
            {
                str(goal)
                for item in selected
                for goal in (item.get("observation_goals") or [])
            }
        )[:12],
        "advisory_only": True,
        "action_kind_changed": False,
        "target_changed": False,
        "automatic_exploitation": False,
        "scope_expansion": False,
    }

    if action.kind not in {"crawl", "scan", "validate"} or not selected:
        return action, context

    max_score = max(int(item.get("score") or 0) for item in selected)
    # Priority is metadata/order only; it is bounded and never outranks safety stops.
    priority = min(99, max(action.priority, 80 + min(15, max_score // 6)))
    families = ", ".join(context["families"])
    prioritized = PlannedAction(
        action.kind,
        action.target,
        f"{action.reason}; public-case focus: {families}",
        priority,
    )
    context["applied"] = True
    return prioritized, context
