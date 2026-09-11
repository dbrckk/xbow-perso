from __future__ import annotations

import hashlib
import json
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


def advisory_focus_fingerprint(advisory: dict[str, Any]) -> str:
    payload = {
        "focus": advisory.get("focus", []),
        "top_n": advisory.get("top_n"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def diff_advisory_focus_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    before_focus = (previous or {}).get("advisory", {}).get("focus", [])
    after_focus = (current or {}).get("advisory", {}).get("focus", [])
    before = {str(item["finding_id"]): item for item in before_focus}
    after = {str(item["finding_id"]): item for item in after_focus}

    before_order = [str(item["finding_id"]) for item in before_focus]
    after_order = [str(item["finding_id"]) for item in after_focus]
    entered = [finding_id for finding_id in after_order if finding_id not in before]
    exited = [finding_id for finding_id in before_order if finding_id not in after]

    rank_changes = []
    for finding_id in sorted(set(before) & set(after)):
        old_rank = int(before[finding_id]["rank"])
        new_rank = int(after[finding_id]["rank"])
        if old_rank != new_rank:
            rank_changes.append(
                {
                    "finding_id": finding_id,
                    "from_rank": old_rank,
                    "to_rank": new_rank,
                    "delta": old_rank - new_rank,
                }
            )

    previous_top = before_order[0] if before_order else None
    current_top = after_order[0] if after_order else None
    top_changed = previous_top != current_top

    displacement = sum(abs(item["delta"]) for item in rank_changes)
    significance_score = min(
        1.0,
        round(
            (0.45 if top_changed else 0.0)
            + min(0.30, 0.10 * (len(entered) + len(exited)))
            + min(0.25, 0.05 * displacement),
            2,
        ),
    )
    significant = significance_score >= 0.45

    return {
        "from_fingerprint": (previous or {}).get("fingerprint"),
        "to_fingerprint": (current or {}).get("fingerprint"),
        "previous_top_finding_id": previous_top,
        "current_top_finding_id": current_top,
        "top_changed": top_changed,
        "entered": entered,
        "exited": exited,
        "rank_changes": rank_changes,
        "significance_score": significance_score,
        "significant": significant,
        "changed": bool(top_changed or entered or exited or rank_changes),
        "read_only": True,
        "advisory_only": True,
    }
