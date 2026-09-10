from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .attack_surface import build_attack_surface
from .evidence_chain import build_evidence_chains
from .hypothesis_engine import build_hypotheses
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import analyze_validation_state

router = APIRouter()


@dataclass(frozen=True)
class CoverageDomain:
    name: str
    observed: int
    reviewed: int
    validated: int
    gaps: int
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def build_red_team_coverage(graph: ObservationGraph) -> dict[str, Any]:
    """Summarize bounded red-team coverage from existing evidence only.

    The model is deliberately read-only. It does not generate payloads, execute
    requests, expand scope, or bypass policy. It measures how much of the already
    observed surface has been reviewed and independently evidenced.
    """
    surface = build_attack_surface(graph)
    hypotheses = build_hypotheses(graph, limit=100)
    chains = build_evidence_chains(graph)
    validation = analyze_validation_state(graph)

    endpoints = surface["summary"]["valid_endpoint_count"]
    technologies = surface["summary"]["technology_count"]
    findings = len(validation.finding_ids)

    input_reviews = sum(item.kind == "input_surface_review" for item in hypotheses)
    authorization_reviews = sum(item.kind == "authorization_surface_review" for item in hypotheses)
    technology_reviews = sum(item.kind == "technology_surface_review" for item in hypotheses)
    validation_gaps = sum(item.kind == "validation_gap" for item in hypotheses)
    complete_chains = sum(item.complete for item in chains)

    endpoint_reviewed_ids = {
        evidence_id
        for item in hypotheses
        if item.kind in {"input_surface_review", "authorization_surface_review"}
        for evidence_id in item.evidence_ids
    }
    technology_reviewed_ids = {
        evidence_id
        for item in hypotheses
        if item.kind == "technology_surface_review"
        for evidence_id in item.evidence_ids
    }

    domains = (
        CoverageDomain(
            name="endpoint_surface",
            observed=endpoints,
            reviewed=len(endpoint_reviewed_ids),
            validated=0,
            gaps=max(0, endpoints - len(endpoint_reviewed_ids)),
            score=_ratio(len(endpoint_reviewed_ids), endpoints),
        ),
        CoverageDomain(
            name="technology_surface",
            observed=technologies,
            reviewed=len(technology_reviewed_ids),
            validated=0,
            gaps=max(0, technologies - len(technology_reviewed_ids)),
            score=_ratio(len(technology_reviewed_ids), technologies),
        ),
        CoverageDomain(
            name="finding_validation",
            observed=findings,
            reviewed=len(validation.attempted_finding_ids),
            validated=len(validation.observed_independent_finding_ids),
            gaps=validation_gaps,
            score=_ratio(len(validation.observed_independent_finding_ids), findings),
        ),
        CoverageDomain(
            name="evidence_quality",
            observed=len(chains),
            reviewed=len(chains),
            validated=complete_chains,
            gaps=max(0, len(chains) - complete_chains),
            score=_ratio(complete_chains, len(chains)),
        ),
    )

    weighted_denominator = sum(max(1, item.observed) for item in domains)
    weighted_score = round(
        sum(item.score * max(1, item.observed) for item in domains) / weighted_denominator,
        4,
    )

    gaps = []
    if surface["summary"]["invalid_endpoint_count"]:
        gaps.append("invalid_endpoints")
    if surface["summary"]["orphan_endpoint_count"]:
        gaps.append("orphan_endpoints")
    if surface["summary"]["host_asset_mismatch_count"]:
        gaps.append("host_asset_mismatch")
    if input_reviews:
        gaps.append("input_review_pending")
    if authorization_reviews:
        gaps.append("authorization_review_pending")
    if technology_reviews:
        gaps.append("technology_review_pending")
    if validation_gaps:
        gaps.append("independent_validation_pending")
    if len(chains) - complete_chains:
        gaps.append("evidence_chain_incomplete")

    return {
        "score": weighted_score,
        "domains": [item.to_dict() for item in domains],
        "gaps": gaps,
        "summary": {
            "observed_endpoints": endpoints,
            "observed_technologies": technologies,
            "observed_findings": findings,
            "independently_validated_findings": len(validation.observed_independent_finding_ids),
            "complete_evidence_chains": complete_chains,
            "pending_hypotheses": len(hypotheses),
        },
        "read_only": True,
        "safe_validation_only": True,
    }


@router.get("/api/campaigns/{campaign_id}/red-team-coverage")
def campaign_red_team_coverage(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    return {
        "campaign_id": campaign.id,
        **build_red_team_coverage(graph),
    }
