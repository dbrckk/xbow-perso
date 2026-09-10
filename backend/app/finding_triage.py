from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .evidence_chain import build_evidence_chains
from .finding_consensus import build_finding_consensus, router as finding_consensus_router
from .finding_correlation import correlate_findings
from .knowledge_memory import build_knowledge_snapshot
from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()
router.routes.extend(finding_consensus_router.routes)

_SEVERITY_WEIGHT = {
    "info": 0.10,
    "low": 0.25,
    "medium": 0.50,
    "high": 0.75,
    "critical": 1.00,
}


@dataclass(frozen=True)
class FindingTriage:
    finding_id: str
    score: float
    severity: str
    confidence: float
    evidence_chain_complete: bool
    source_consensus_score: float
    corroborated: bool
    duplicate_candidate: bool
    duplicate_group_size: int
    recommended_state: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_finding_triage(findings: list[Any], graph: ObservationGraph) -> list[FindingTriage]:
    """Rank findings using impact, evidence quality and duplicate pressure.

    This is an advisory, read-only ranking layer. It never confirms findings,
    merges records, queues jobs, or performs target actions.
    """
    confidence_by_id = {
        item.finding_id: item.score
        for item in build_knowledge_snapshot(graph).finding_confidence
    }
    consensus_by_id = {
        item.finding_id: item
        for item in build_finding_consensus(graph)
    }
    chains = {item.finding_id: item for item in build_evidence_chains(graph)}
    observed_finding_ids = {item.id for item in graph.by_kind("finding")}
    duplicate_size: dict[str, int] = {}
    for group in correlate_findings(findings):
        size = len(group.finding_ids)
        for finding_id in group.finding_ids:
            duplicate_size[finding_id] = size

    ranked: list[FindingTriage] = []
    for finding in findings:
        finding_id = str(finding.id)
        graph_id = f"finding:{finding_id}"
        severity = str(finding.severity)
        severity_weight = _SEVERITY_WEIGHT.get(severity, 0.0)
        confidence = confidence_by_id.get(graph_id, 0.0)
        consensus = consensus_by_id.get(finding_id)
        consensus_score = consensus.score if consensus else 0.0
        corroborated = bool(consensus and consensus.corroborated)
        chain = chains.get(graph_id)
        chain_complete = bool(chain and chain.complete)
        group_size = duplicate_size.get(finding_id, 1)
        duplicate = group_size > 1
        observed = graph_id in observed_finding_ids

        evidence_gap = 1.0 - confidence
        chain_gap = 0.0 if chain_complete else 1.0
        duplicate_discount = min(0.15, 0.05 * max(0, group_size - 1))
        score = round(
            max(
                0.0,
                min(
                    1.0,
                    (severity_weight * 0.55)
                    + (evidence_gap * 0.30)
                    + (chain_gap * 0.15)
                    - duplicate_discount,
                ),
            ),
            4,
        )

        if str(finding.status) in {"confirmed", "rejected"} and chain_complete:
            recommended = "resolved"
        elif duplicate and not observed:
            recommended = "review_duplicate"
        elif not chain_complete or confidence < 0.75 or not corroborated:
            recommended = "validate"
        elif duplicate:
            recommended = "review_duplicate"
        else:
            recommended = "review_for_report"

        ranked.append(
            FindingTriage(
                finding_id=finding_id,
                score=score,
                severity=severity,
                confidence=confidence,
                evidence_chain_complete=chain_complete,
                source_consensus_score=consensus_score,
                corroborated=corroborated,
                duplicate_candidate=duplicate,
                duplicate_group_size=group_size,
                recommended_state=recommended,
            )
        )

    return sorted(ranked, key=lambda item: (-item.score, item.finding_id))


@router.get("/api/campaigns/{campaign_id}/finding-triage")
def campaign_finding_triage(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    triage = build_finding_triage(campaign.findings, graph)
    return {
        "campaign_id": campaign.id,
        "findings": [item.to_dict() for item in triage],
        "summary": {
            "total": len(triage),
            "needs_validation": sum(item.recommended_state == "validate" for item in triage),
            "duplicate_review": sum(item.recommended_state == "review_duplicate" for item in triage),
            "report_review": sum(item.recommended_state == "review_for_report" for item in triage),
            "corroborated": sum(item.corroborated for item in triage),
        },
        "read_only": True,
        "advisory_only": True,
    }
