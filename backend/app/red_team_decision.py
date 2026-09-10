from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal

from fastapi import APIRouter

from .attack_surface import build_attack_surface
from .evidence_chain import build_evidence_chains
from .finding_triage import build_finding_triage
from .hypothesis_engine import build_hypotheses
from .observation_graph import ObservationGraph, load_observation_graph
from .red_team_coverage import build_red_team_coverage

DecisionKind = Literal[
    "scope_integrity",
    "validate_findings",
    "strengthen_evidence",
    "review_surface",
    "review_for_report",
    "idle",
]

router = APIRouter()


@dataclass(frozen=True)
class RedTeamDecision:
    kind: DecisionKind
    priority: float
    reason: str
    finding_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    blocked_from_execution: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["finding_ids"] = list(self.finding_ids)
        payload["evidence_ids"] = list(self.evidence_ids)
        return payload


def build_red_team_decisions(
    findings: list[Any],
    graph: ObservationGraph,
    *,
    scope_checker: Callable[[str], bool] | None = None,
    limit: int = 10,
) -> list[RedTeamDecision]:
    """Rank safe red-team work from existing state without executing target actions."""
    if not 1 <= limit <= 25:
        raise ValueError("decision limit must be between 1 and 25")

    surface = build_attack_surface(graph, scope_checker=scope_checker)
    coverage = build_red_team_coverage(graph, scope_checker=scope_checker)
    triage = build_finding_triage(findings, graph)
    chains = build_evidence_chains(graph)
    hypotheses = build_hypotheses(graph, limit=100, scope_checker=scope_checker)
    decisions: list[RedTeamDecision] = []

    integrity_count = (
        surface["summary"]["invalid_endpoint_count"]
        + surface["summary"]["out_of_scope_endpoint_count"]
        + surface["summary"]["host_asset_mismatch_count"]
    )
    if integrity_count:
        decisions.append(
            RedTeamDecision(
                kind="scope_integrity",
                priority=1.0,
                reason="attack-surface integrity must be resolved before further review",
            )
        )

    validation_ids = tuple(
        item.finding_id for item in triage if item.recommended_state == "validate"
    )
    if validation_ids:
        decisions.append(
            RedTeamDecision(
                kind="validate_findings",
                priority=0.92,
                reason="high-value findings still require independent validation",
                finding_ids=validation_ids[:10],
            )
        )

    incomplete = [item for item in chains if not item.complete]
    if incomplete:
        decisions.append(
            RedTeamDecision(
                kind="strengthen_evidence",
                priority=0.84,
                reason="finding support chains are incomplete",
                finding_ids=tuple(item.finding_id.removeprefix("finding:") for item in incomplete[:10]),
            )
        )

    surface_hypotheses = [
        item
        for item in hypotheses
        if item.kind in {
            "input_surface_review",
            "authorization_surface_review",
            "technology_surface_review",
        }
    ]
    if surface_hypotheses:
        decisions.append(
            RedTeamDecision(
                kind="review_surface",
                priority=0.72,
                reason="in-scope observed surface still has bounded review opportunities",
                evidence_ids=tuple(
                    evidence_id
                    for item in surface_hypotheses[:10]
                    for evidence_id in item.evidence_ids
                ),
            )
        )

    report_ids = tuple(
        item.finding_id for item in triage if item.recommended_state == "review_for_report"
    )
    if report_ids:
        decisions.append(
            RedTeamDecision(
                kind="review_for_report",
                priority=0.64,
                reason="validated findings are ready for human report review",
                finding_ids=report_ids[:10],
            )
        )

    if not decisions:
        decisions.append(
            RedTeamDecision(
                kind="idle",
                priority=0.0,
                reason="no additional bounded red-team review work is currently indicated",
            )
        )

    coverage_penalty = max(0.0, 1.0 - float(coverage["score"]))
    adjusted = []
    for item in decisions:
        if item.kind in {"validate_findings", "strengthen_evidence", "review_surface"}:
            priority = min(1.0, round(item.priority + coverage_penalty * 0.05, 4))
            adjusted.append(RedTeamDecision(**{**asdict(item), "priority": priority}))
        else:
            adjusted.append(item)

    return sorted(adjusted, key=lambda item: (-item.priority, item.kind))[:limit]


@router.get("/api/campaigns/{campaign_id}/red-team-decisions")
def campaign_red_team_decisions(campaign_id: str, limit: int = 10):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    decisions = build_red_team_decisions(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
        limit=limit,
    )
    return {
        "campaign_id": campaign.id,
        "decisions": [item.to_dict() for item in decisions],
        "summary": {
            "total": len(decisions),
            "highest_priority": max((item.priority for item in decisions), default=0.0),
            "next_focus": decisions[0].kind if decisions else "idle",
        },
        "read_only": True,
        "advisory_only": True,
        "scope_aware": True,
    }
