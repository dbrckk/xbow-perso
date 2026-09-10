from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .observation_graph import ObservationGraph, load_observation_graph
from .red_team_decision import RedTeamDecision, build_red_team_decisions

router = APIRouter()

_BLOCKING_KINDS = {"scope_integrity"}
_ACTIONABLE_KINDS = {
    "validate_findings",
    "strengthen_evidence",
    "review_surface",
    "review_for_report",
}


@dataclass(frozen=True)
class DecisionConsensus:
    next_focus: str
    confidence: float
    blocked: bool
    contradictory: bool
    reasons: tuple[str, ...]
    supporting_kinds: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["supporting_kinds"] = list(self.supporting_kinds)
        return payload


def build_decision_consensus(decisions: list[RedTeamDecision]) -> DecisionConsensus:
    """Resolve advisory decisions conservatively without executing any action."""
    if not decisions:
        return DecisionConsensus("idle", 1.0, False, False, ("no decision signals",), ())

    kinds = tuple(sorted({item.kind for item in decisions}))
    blocking = [item for item in decisions if item.kind in _BLOCKING_KINDS]
    actionable = [item for item in decisions if item.kind in _ACTIONABLE_KINDS]

    if blocking:
        return DecisionConsensus(
            next_focus="scope_integrity",
            confidence=1.0,
            blocked=True,
            contradictory=bool(actionable),
            reasons=("scope integrity signal blocks downstream review",),
            supporting_kinds=kinds,
        )

    ranked = sorted(decisions, key=lambda item: (-item.priority, item.kind))
    top = ranked[0]
    close_competitors = [
        item
        for item in ranked[1:]
        if top.priority - item.priority <= 0.05 and item.kind != top.kind
    ]
    contradictory = bool(close_competitors)
    confidence = round(
        max(0.0, min(1.0, top.priority - (0.15 if contradictory else 0.0))),
        4,
    )
    reasons = [top.reason]
    if contradictory:
        reasons.append("multiple near-equal decision signals require conservative review")

    return DecisionConsensus(
        next_focus=top.kind,
        confidence=confidence,
        blocked=contradictory,
        contradictory=contradictory,
        reasons=tuple(reasons),
        supporting_kinds=kinds,
    )


@router.get("/api/campaigns/{campaign_id}/decision-consensus")
def campaign_decision_consensus(campaign_id: str):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph: ObservationGraph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    decisions = build_red_team_decisions(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
        limit=10,
    )
    consensus = build_decision_consensus(decisions)
    return {
        "campaign_id": campaign.id,
        "consensus": consensus.to_dict(),
        "read_only": True,
        "advisory_only": True,
        "fail_closed": True,
    }
