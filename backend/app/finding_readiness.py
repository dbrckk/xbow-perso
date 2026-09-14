from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .evidence_quality import build_evidence_quality
from .finding_consensus import build_finding_consensus
from .hypothesis_memory import summarize_hypothesis_stability
from .knowledge_memory import build_knowledge_snapshot, severity_weight
from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()


@dataclass(frozen=True)
class FindingReadiness:
    finding_id: str
    readiness_score: float
    readiness: str
    severity_weight: float
    confidence: float
    evidence_quality: float
    consensus_score: float
    stability_score: float
    contradictory: bool
    blockers: tuple[str, ...]
    components: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


def build_finding_readiness(
    findings: list[Any],
    graph: ObservationGraph,
    *,
    hypothesis_snapshots: list[dict[str, Any]] | None = None,
) -> list[FindingReadiness]:
    """Build an explainable, read-only readiness verdict for each finding."""
    confidence_by_id = {
        item.finding_id.removeprefix("finding:"): item.score
        for item in build_knowledge_snapshot(graph).finding_confidence
    }
    quality_by_id = {
        item.finding_id: item
        for item in build_evidence_quality(graph)
    }
    consensus_by_id = {
        item.finding_id: item
        for item in build_finding_consensus(graph)
    }
    stability_by_id = {
        item["finding_id"]: item
        for item in summarize_hypothesis_stability(hypothesis_snapshots or [])
    }

    results: list[FindingReadiness] = []
    for finding in findings:
        finding_id = str(finding.id)
        confidence = float(confidence_by_id.get(finding_id, 0.0))
        quality = quality_by_id.get(finding_id)
        consensus = consensus_by_id.get(finding_id)
        stability = stability_by_id.get(finding_id, {})

        evidence_quality = float(quality.score if quality else 0.0)
        consensus_score = float(consensus.score if consensus else 0.0)
        stability_score = float(stability.get("stability_score", 0.0))
        contradictory = stability.get("stability") == "contradictory"

        components = {
            "confidence": round(confidence * 0.35, 4),
            "evidence_quality": round(evidence_quality * 0.30, 4),
            "consensus": round(consensus_score * 0.20, 4),
            "stability": round(stability_score * 0.15, 4),
        }
        score = round(sum(components.values()), 4)

        blockers: list[str] = []
        if confidence < 0.75:
            blockers.append("insufficient_confidence")
        if evidence_quality < 0.80:
            blockers.append("insufficient_evidence_quality")
        if not consensus or not consensus.corroborated:
            blockers.append("insufficient_independent_corroboration")
        if contradictory:
            blockers.append("contradictory_history")
        if stability and stability.get("stability") not in {"stable", "fresh", "evolving"}:
            if "contradictory_history" not in blockers:
                blockers.append("unstable_history")

        if contradictory:
            readiness = "blocked"
        elif not blockers and score >= 0.80:
            readiness = "report_review_ready"
        elif score >= 0.55:
            readiness = "needs_review"
        else:
            readiness = "needs_validation"

        results.append(
            FindingReadiness(
                finding_id=finding_id,
                readiness_score=score,
                readiness=readiness,
                severity_weight=severity_weight(getattr(finding, "severity", "")),
                confidence=confidence,
                evidence_quality=evidence_quality,
                consensus_score=consensus_score,
                stability_score=stability_score,
                contradictory=contradictory,
                blockers=tuple(blockers),
                components=components,
            )
        )

    return sorted(
        results,
        key=lambda item: (
            item.readiness == "blocked",
            -item.readiness_score,
            item.finding_id,
        ),
    )


@router.get("/api/campaigns/{campaign_id}/finding-readiness")
def campaign_finding_readiness(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    store = storage()
    graph = load_observation_graph(store, campaign.id)
    snapshots = store.list_hypothesis_snapshots(campaign.id, limit=50)
    readiness = build_finding_readiness(
        campaign.findings,
        graph,
        hypothesis_snapshots=snapshots,
    )

    return {
        "campaign_id": campaign.id,
        "findings": [item.to_dict() for item in readiness],
        "summary": {
            "total": len(readiness),
            "report_review_ready": sum(item.readiness == "report_review_ready" for item in readiness),
            "needs_review": sum(item.readiness == "needs_review" for item in readiness),
            "needs_validation": sum(item.readiness == "needs_validation" for item in readiness),
            "blocked": sum(item.readiness == "blocked" for item in readiness),
            "contradictory": sum(item.contradictory for item in readiness),
        },
        "read_only": True,
        "advisory_only": True,
        "does_not_confirm_findings": True,
    }
