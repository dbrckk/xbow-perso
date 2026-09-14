from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()


@dataclass(frozen=True)
class FindingConsensus:
    finding_id: str
    source_count: int
    independent_validator_count: int
    evidence_backed_validator_count: int
    evidence_source_count: int
    corroborated: bool
    consensus_level: str
    score: float
    sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sources"] = list(self.sources)
        return payload


def _children(graph: ObservationGraph) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for item in graph.values():
        for parent_id in item.parent_ids:
            result.setdefault(parent_id, []).append(item)
    return result


def build_finding_consensus(graph: ObservationGraph) -> list[FindingConsensus]:
    """Measure independent corroboration of findings from recorded observations only."""
    children = _children(graph)
    results: list[FindingConsensus] = []

    for finding in graph.by_kind("finding"):
        validations = [
            item
            for item in children.get(finding.id, [])
            if item.kind == "validation" and item.value == "observed"
        ]
        independent_validations = [item for item in validations if item.source != finding.source]

        evidence_by_validation: dict[str, list[Any]] = {
            validation.id: [
                item
                for item in children.get(validation.id, [])
                if item.kind == "evidence"
            ]
            for validation in independent_validations
        }
        evidence = [
            item
            for validation_evidence in evidence_by_validation.values()
            for item in validation_evidence
        ]

        validator_sources = {item.source for item in independent_validations}
        evidence_backed_validator_sources = {
            validation.source
            for validation in independent_validations
            if evidence_by_validation.get(validation.id)
        }
        evidence_sources = {item.source for item in evidence}
        all_sources = {finding.source, *validator_sources, *evidence_sources}

        corroborated = bool(evidence_backed_validator_sources)
        if len(evidence_backed_validator_sources) >= 2:
            consensus_level = "quorum"
        elif evidence_backed_validator_sources:
            consensus_level = "single_evidence_backed_validator"
        else:
            consensus_level = "none"

        score = 0.30
        if independent_validations:
            score += 0.25
        if evidence_backed_validator_sources:
            score += 0.20
        if evidence:
            score += 0.10
        if len(validator_sources) >= 2:
            score += 0.10
        if len(evidence_sources) >= 2:
            score += 0.05

        results.append(
            FindingConsensus(
                finding_id=finding.id.removeprefix("finding:"),
                source_count=len(all_sources),
                independent_validator_count=len(validator_sources),
                evidence_backed_validator_count=len(evidence_backed_validator_sources),
                evidence_source_count=len(evidence_sources),
                corroborated=corroborated,
                consensus_level=consensus_level,
                score=min(1.0, round(score, 4)),
                sources=tuple(sorted(all_sources)),
            )
        )

    return sorted(results, key=lambda item: (-item.score, item.finding_id))


@router.get("/api/campaigns/{campaign_id}/finding-consensus")
def campaign_finding_consensus(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    consensus = build_finding_consensus(graph)
    return {
        "campaign_id": campaign.id,
        "findings": [item.to_dict() for item in consensus],
        "summary": {
            "total": len(consensus),
            "corroborated": sum(item.corroborated for item in consensus),
            "quorum": sum(item.consensus_level == "quorum" for item in consensus),
            "single_evidence_backed_validator": sum(
                item.consensus_level == "single_evidence_backed_validator"
                for item in consensus
            ),
            "single_source": sum(item.source_count == 1 for item in consensus),
            "highest_score": max((item.score for item in consensus), default=0.0),
        },
        "read_only": True,
        "evidence_backed": True,
    }
