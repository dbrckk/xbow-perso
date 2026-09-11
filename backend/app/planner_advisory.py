from __future__ import annotations

from typing import Any

from .knowledge_memory import rank_findings_explainable
from .observation_graph import ObservationGraph


def build_advisory_planner_context(
    campaign: Any,
    graph: ObservationGraph,
    *,
    stability: dict[str, dict[str, Any]] | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """Build a read-only focus context for the deterministic planner.

    This context may explain and order human review attention, but it never
    authorizes execution or changes the planner's allowed action set.
    """
    if not 1 <= top_n <= 10:
        raise ValueError("top_n must be between 1 and 10")

    ranking = rank_findings_explainable(
        list(getattr(campaign, "findings", ())),
        graph,
        stability=stability,
    )
    selected = ranking[:top_n]
    top = selected[0] if selected else None

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

    focus_items = [
        {
            "rank": index,
            "finding_id": item["finding_id"],
            "score": item["score"],
            "severity": item["severity"],
            "confidence": item["confidence"],
            "stability": item["stability"],
            "components": item["components"],
            "reason": (
                f"rank={index}; score={item['score']:.4f}; "
                f"severity={item['severity']}; confidence={item['confidence']:.2f}; "
                f"stability={item['stability']}"
            ),
        }
        for index, item in enumerate(selected, start=1)
    ]

    return {
        "focus_finding_id": focus,
        "focus": focus_items,
        "focus_count": len(focus_items),
        "top_n": top_n,
        "rationale": rationale,
        "ranking": ranking,
        "read_only": True,
        "advisory_only": True,
    }
