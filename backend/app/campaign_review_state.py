from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter

from .finding_lifecycle import build_finding_lifecycle
from .observation_graph import ObservationGraph, load_observation_graph
from .report_readiness import build_report_readiness

router = APIRouter()


def build_campaign_review_state(findings: list[Any], graph: ObservationGraph) -> dict[str, Any]:
    """Aggregate human-review state from existing finding evidence only.

    This summary is read-only and advisory. It cannot mutate findings, approve
    reports, submit reports, queue target actions, or execute against targets.
    """
    lifecycle = build_finding_lifecycle(findings, graph)
    readiness = build_report_readiness(findings, graph)

    blockers = Counter(
        blocker
        for item in readiness
        for blocker in item.blockers
    )
    prerequisites = Counter(
        prerequisite
        for item in lifecycle
        for prerequisite in item.prerequisites
    )

    ready_ids = tuple(
        item.finding_id for item in readiness if item.ready_for_human_review
    )
    human_decision_ids = tuple(
        item.finding_id for item in lifecycle if item.human_decision_required
    )
    transition_ids = tuple(
        item.finding_id for item in lifecycle if item.transition_allowed
    )

    next_focus = "idle"
    if blockers.get("missing_independent_validation"):
        next_focus = "independent_validation"
    elif blockers.get("incomplete_evidence_chain"):
        next_focus = "evidence_integrity"
    elif blockers.get("duplicate_review_required"):
        next_focus = "duplicate_review"
    elif ready_ids:
        next_focus = "human_report_review"
    elif human_decision_ids:
        next_focus = "human_finding_decision"
    elif transition_ids:
        next_focus = "finding_state_review"

    return {
        "total_findings": len(findings),
        "ready_for_human_review": len(ready_ids),
        "blocked_from_human_review": len(readiness) - len(ready_ids),
        "human_decision_required": len(human_decision_ids),
        "transition_allowed": len(transition_ids),
        "graph_missing": sum(not item.graph_observed for item in lifecycle),
        "chain_integrity_failures": sum(
            not item.evidence_chain_integrity_ok for item in lifecycle
        ),
        "ready_finding_ids": list(ready_ids),
        "human_decision_finding_ids": list(human_decision_ids),
        "blockers": dict(sorted(blockers.items())),
        "prerequisites": dict(sorted(prerequisites.items())),
        "next_focus": next_focus,
        "read_only": True,
        "advisory_only": True,
        "human_approval_required": True,
        "execution_authority": False,
    }


@router.get("/api/campaigns/{campaign_id}/review-state")
def campaign_review_state(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    return {
        "campaign_id": campaign.id,
        "review_state": build_campaign_review_state(campaign.findings, graph),
    }
