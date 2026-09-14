from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .finding_correlation import cluster_findings
from .finding_readiness import build_finding_readiness
from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()


@dataclass(frozen=True)
class ClusterConsensus:
    cluster_id: str
    finding_ids: tuple[str, ...]
    cluster_confidence: float
    mean_readiness: float
    min_readiness: float
    max_readiness: float
    report_ready_count: int
    needs_validation_count: int
    blocked_count: int
    contradictory_count: int
    status: str
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["finding_ids"] = list(self.finding_ids)
        payload["blockers"] = list(self.blockers)
        return payload


def build_cluster_consensus(
    findings: list[Any],
    graph: ObservationGraph,
    *,
    hypothesis_snapshots: list[dict[str, Any]] | None = None,
    threshold: float = 0.75,
) -> list[ClusterConsensus]:
    """Aggregate finding readiness conservatively at cluster level."""
    clusters, _similarities = cluster_findings(findings, threshold=threshold)
    readiness = {
        item.finding_id: item
        for item in build_finding_readiness(
            findings,
            graph,
            hypothesis_snapshots=hypothesis_snapshots,
        )
    }

    results: list[ClusterConsensus] = []
    for cluster in clusters:
        members = [
            readiness[finding_id]
            for finding_id in cluster.finding_ids
            if finding_id in readiness
        ]
        scores = [item.readiness_score for item in members]
        mean_readiness = round(sum(scores) / len(scores), 4) if scores else 0.0
        min_readiness = round(min(scores), 4) if scores else 0.0
        max_readiness = round(max(scores), 4) if scores else 0.0

        report_ready_count = sum(item.readiness == "report_review_ready" for item in members)
        needs_validation_count = sum(item.readiness == "needs_validation" for item in members)
        blocked_count = sum(item.readiness == "blocked" for item in members)
        contradictory_count = sum(item.contradictory for item in members)

        blockers: list[str] = []
        if contradictory_count:
            blockers.append("cluster_contains_contradictory_history")
        if blocked_count:
            blockers.append("cluster_contains_blocked_finding")
        if needs_validation_count:
            blockers.append("cluster_contains_unvalidated_finding")
        if report_ready_count != len(members):
            blockers.append("cluster_not_uniformly_report_ready")

        if contradictory_count or blocked_count:
            status = "blocked"
        elif members and report_ready_count == len(members) and min_readiness >= 0.80:
            status = "report_review_ready"
        elif members and mean_readiness >= 0.55:
            status = "needs_review"
        else:
            status = "needs_validation"

        results.append(
            ClusterConsensus(
                cluster_id=cluster.cluster_id,
                finding_ids=cluster.finding_ids,
                cluster_confidence=cluster.confidence,
                mean_readiness=mean_readiness,
                min_readiness=min_readiness,
                max_readiness=max_readiness,
                report_ready_count=report_ready_count,
                needs_validation_count=needs_validation_count,
                blocked_count=blocked_count,
                contradictory_count=contradictory_count,
                status=status,
                blockers=tuple(blockers),
            )
        )

    return sorted(
        results,
        key=lambda item: (
            item.status != "blocked",
            -item.cluster_confidence,
            item.cluster_id,
        ),
    )


@router.get("/api/campaigns/{campaign_id}/finding-cluster-consensus")
def campaign_finding_cluster_consensus(campaign_id: str, threshold: float = 0.75):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    store = storage()
    graph = load_observation_graph(store, campaign.id)
    snapshots = store.list_hypothesis_snapshots(campaign.id, limit=50)
    consensus = build_cluster_consensus(
        campaign.findings,
        graph,
        hypothesis_snapshots=snapshots,
        threshold=threshold,
    )
    return {
        "campaign_id": campaign.id,
        "threshold": threshold,
        "clusters": [item.to_dict() for item in consensus],
        "summary": {
            "clusters": len(consensus),
            "report_review_ready": sum(item.status == "report_review_ready" for item in consensus),
            "needs_review": sum(item.status == "needs_review" for item in consensus),
            "needs_validation": sum(item.status == "needs_validation" for item in consensus),
            "blocked": sum(item.status == "blocked" for item in consensus),
            "contradictory": sum(item.contradictory_count > 0 for item in consensus),
        },
        "read_only": True,
        "advisory_only": True,
        "auto_merge": False,
        "does_not_propagate_member_state": True,
    }
