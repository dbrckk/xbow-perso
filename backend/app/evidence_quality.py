from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .evidence_chain import build_evidence_chains
from .finding_consensus import build_finding_consensus
from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()


@dataclass(frozen=True)
class EvidenceQuality:
    finding_id: str
    score: float
    grade: str
    independent_validation: bool
    artifact_backed: bool
    source_count: int
    chain_integrity: bool
    corroborated: bool
    components: dict[str, float]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = list(self.issues)
        return payload


def _grade(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def build_evidence_quality(graph: ObservationGraph) -> list[EvidenceQuality]:
    """Score recorded evidence quality without changing finding state or executing work."""
    chains = {item.finding_id: item for item in build_evidence_chains(graph)}
    consensus = {
        f"finding:{item.finding_id}": item
        for item in build_finding_consensus(graph)
    }
    by_id = {item.id: item for item in graph.values()}
    results: list[EvidenceQuality] = []

    for finding in graph.by_kind("finding"):
        chain = chains.get(finding.id)
        finding_consensus = consensus.get(finding.id)

        validation_ids = set(chain.validation_ids if chain else ())
        evidence_items = [
            by_id[item_id]
            for item_id in (chain.evidence_ids if chain else ())
            if item_id in by_id
        ]
        artifact_backed = any(
            item.metadata.get("artifact_id")
            or item.metadata.get("artifact_kind") == "validation"
            for item in evidence_items
        )
        independent = bool(chain and chain.independent_validation_observed)
        source_count = int(chain.source_count if chain else 0)
        chain_integrity = bool(
            chain
            and chain.ancestor_ids
            and not chain.dangling_parent_ids
            and not chain.cycle_detected
        )
        corroborated = bool(finding_consensus and finding_consensus.corroborated)

        components = {
            "independent_validation": 0.35 if independent else 0.0,
            "artifact_backing": (
                0.25
                if artifact_backed
                else (0.10 if evidence_items else 0.0)
            ),
            "source_diversity": (
                0.20 if source_count >= 3 else (0.10 if source_count >= 2 else 0.0)
            ),
            "chain_integrity": 0.15 if chain_integrity else 0.0,
            "corroboration": 0.05 if corroborated else 0.0,
        }
        score = round(min(1.0, sum(components.values())), 4)

        issues: list[str] = []
        if not independent:
            issues.append("missing_independent_observed_validation")
        if not evidence_items:
            issues.append("missing_linked_evidence")
        elif not artifact_backed:
            issues.append("evidence_not_artifact_backed")
        if source_count < 2:
            issues.append("low_source_diversity")
        if not chain_integrity:
            issues.append("incomplete_or_corrupt_chain")
        if not corroborated:
            issues.append("not_corroborated")

        results.append(
            EvidenceQuality(
                finding_id=finding.id.removeprefix("finding:"),
                score=score,
                grade=_grade(score),
                independent_validation=independent,
                artifact_backed=artifact_backed,
                source_count=source_count,
                chain_integrity=chain_integrity,
                corroborated=corroborated,
                components=components,
                issues=tuple(issues),
            )
        )

    return sorted(results, key=lambda item: (item.score, item.finding_id))


@router.get("/api/campaigns/{campaign_id}/evidence-quality")
def campaign_evidence_quality(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    quality = build_evidence_quality(graph)
    return {
        "campaign_id": campaign.id,
        "findings": [item.to_dict() for item in quality],
        "summary": {
            "total": len(quality),
            "high": sum(item.grade == "high" for item in quality),
            "medium": sum(item.grade == "medium" for item in quality),
            "low": sum(item.grade == "low" for item in quality),
            "artifact_backed": sum(item.artifact_backed for item in quality),
            "corroborated": sum(item.corroborated for item in quality),
        },
        "read_only": True,
        "advisory_only": True,
    }
