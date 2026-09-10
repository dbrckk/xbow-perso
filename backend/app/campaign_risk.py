from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal

from fastapi import APIRouter

from .attack_surface import build_attack_surface
from .decision_consensus import build_decision_consensus
from .finding_triage import build_finding_triage
from .observation_graph import ObservationGraph, load_observation_graph
from .red_team_coverage import build_red_team_coverage
from .red_team_decision import build_red_team_decisions

RiskLevel = Literal["low", "moderate", "high", "critical"]

router = APIRouter()


@dataclass(frozen=True)
class CampaignRisk:
    level: RiskLevel
    score: float
    confidence: float
    blocked: bool
    factors: tuple[str, ...]
    next_focus: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["factors"] = list(self.factors)
        return payload


def build_campaign_risk(
    findings: list[Any],
    graph: ObservationGraph,
    *,
    scope_checker: Callable[[str], bool] | None = None,
) -> CampaignRisk:
    """Summarize campaign review risk from existing evidence only.

    This model is advisory and read-only. It never changes finding state, creates
    payloads, queues work, or performs target actions.
    """
    surface = build_attack_surface(graph, scope_checker=scope_checker)
    coverage = build_red_team_coverage(graph, scope_checker=scope_checker)
    triage = build_finding_triage(findings, graph)
    decisions = build_red_team_decisions(
        findings,
        graph,
        scope_checker=scope_checker,
        limit=10,
    )
    consensus = build_decision_consensus(decisions)

    factors: list[str] = []
    integrity_count = (
        surface["summary"]["invalid_endpoint_count"]
        + surface["summary"]["out_of_scope_endpoint_count"]
        + surface["summary"]["host_asset_mismatch_count"]
    )
    if integrity_count:
        factors.append("scope_or_surface_integrity")

    needs_validation = sum(item.recommended_state == "validate" for item in triage)
    if needs_validation:
        factors.append("unvalidated_findings")

    high_value = [item for item in triage if item.severity in {"high", "critical"}]
    if high_value:
        factors.append("high_impact_findings")

    duplicate_review = sum(
        item.recommended_state == "review_duplicate" for item in triage
    )
    if duplicate_review:
        factors.append("duplicate_pressure")

    if float(coverage["score"]) < 0.5:
        factors.append("low_review_coverage")
    if consensus.blocked:
        factors.append("decision_consensus_blocked")

    highest_triage = max((item.score for item in triage), default=0.0)
    coverage_gap = 1.0 - float(coverage["score"])
    integrity_pressure = min(1.0, integrity_count / 3)
    consensus_pressure = 1.0 if consensus.blocked else 0.0
    score = round(
        min(
            1.0,
            (highest_triage * 0.45)
            + (coverage_gap * 0.25)
            + (integrity_pressure * 0.20)
            + (consensus_pressure * 0.10),
        ),
        4,
    )

    if score >= 0.85 or integrity_count >= 2:
        level: RiskLevel = "critical"
    elif score >= 0.65:
        level = "high"
    elif score >= 0.35:
        level = "moderate"
    else:
        level = "low"

    confidence = round(
        max(
            0.0,
            min(
                1.0,
                (float(coverage["score"]) * 0.60)
                + (consensus.confidence * 0.40),
            ),
        ),
        4,
    )

    return CampaignRisk(
        level=level,
        score=score,
        confidence=confidence,
        blocked=bool(integrity_count or consensus.blocked),
        factors=tuple(factors),
        next_focus=consensus.next_focus,
    )


@router.get("/api/campaigns/{campaign_id}/risk")
def campaign_risk(campaign_id: str):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    risk = build_campaign_risk(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
    )
    return {
        "campaign_id": campaign.id,
        "risk": risk.to_dict(),
        "read_only": True,
        "advisory_only": True,
        "scope_aware": True,
    }
