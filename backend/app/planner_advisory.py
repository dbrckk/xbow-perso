from __future__ import annotations

from typing import Any

from .knowledge_memory import rank_findings_explainable
from .observation_graph import ObservationGraph


def build_advisory_planner_context(
    campaign: Any,
    graph: ObservationGraph,
    *,
    stability: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a read-only focus context for the deterministic planner.

    This context may explain and order human review attention, but it never
    authorizes execution or changes the planner's allowed action set.
    """
    ranking = rank_findings_explainable(
        list(getattr(campaign, "findings", ())),
        graph,
        stability=stability,
    )
    top = ranking[0] if ranking else None

    if top is None:
        focus = None
        rationale = "no findings are available for advisory prioritization"
    else:
        focus = top["finding_id"]
        rationale = (
            f"highest advisory score={top['score']:.4f}; "
            f"severity={top['severity']}; "
            f"confidence={top['confidence']:.2f}; "
            f"stability={top['stability']}"
        )

    return {
        "focus_finding_id": focus,
        "rationale": rationale,
        "ranking": ranking,
        "read_only": True,
        "advisory_only": True,
    }
