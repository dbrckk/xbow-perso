from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .differential_intelligence import DifferentialSignal, build_differential_signals
from .finding_cluster_consensus import build_cluster_consensus
from .finding_cluster_saturation import build_cluster_saturation
from .finding_correlation import cluster_findings
from .finding_readiness import build_finding_readiness
from .finding_triage import build_finding_triage
from .observation_graph import load_observation_graph

router = APIRouter()


def build_finding_intelligence(
    findings: list[Any],
    graph: Any,
    *,
    hypothesis_snapshots: list[dict[str, Any]] | None = None,
    threshold: float = 0.75,
) -> dict[str, Any]:
    readiness = build_finding_readiness(
        findings,
        graph,
        hypothesis_snapshots=hypothesis_snapshots,
    )
    triage = build_finding_triage(findings, graph)
    clusters, similarities = cluster_findings(findings, threshold=threshold)
    cluster_consensus = build_cluster_consensus(
        findings,
        graph,
        hypothesis_snapshots=hypothesis_snapshots,
        threshold=threshold,
    )
    saturation = build_cluster_saturation(
        findings,
        graph,
        threshold=threshold,
    )
    differential_signals = build_differential_signals(graph)

    readiness_by_id = {item.finding_id: item for item in readiness}
    triage_by_id = {item.finding_id: item for item in triage}
    cluster_by_member = {
        finding_id: cluster
        for cluster in clusters
        for finding_id in cluster.finding_ids
    }
    consensus_by_cluster = {item.cluster_id: item for item in cluster_consensus}
    saturation_by_cluster = {item.cluster_id: item for item in saturation}

    finding_rows = []
    for finding in sorted(findings, key=lambda item: str(item.id)):
        finding_id = str(finding.id)
        readiness_item = readiness_by_id.get(finding_id)
        triage_item = triage_by_id.get(finding_id)
        cluster = cluster_by_member.get(finding_id)
        cluster_id = cluster.cluster_id if cluster else None
        differential_item = differential_signals.get(
            finding_id,
            DifferentialSignal(finding_id=finding_id, signal="none"),
        )
        finding_rows.append(
            {
                "finding_id": finding_id,
                "severity": str(getattr(finding, "severity", "")),
                "status": str(getattr(finding, "status", "")),
                "readiness": readiness_item.to_dict() if readiness_item else None,
                "triage": triage_item.to_dict() if triage_item else None,
                "differential": differential_item.to_dict(),
                "cluster_id": cluster_id,
                "cluster_status": (
                    consensus_by_cluster[cluster_id].status
                    if cluster_id in consensus_by_cluster
                    else None
                ),
                "cluster_saturated": (
                    saturation_by_cluster[cluster_id].saturated
                    if cluster_id in saturation_by_cluster
                    else False
                ),
            }
        )

    cluster_rows = []
    for cluster in clusters:
        consensus = consensus_by_cluster.get(cluster.cluster_id)
        saturated = saturation_by_cluster.get(cluster.cluster_id)
        cluster_rows.append(
            {
                "cluster": cluster.to_dict(),
                "consensus": consensus.to_dict() if consensus else None,
                "saturation": saturated.to_dict() if saturated else None,
            }
        )

    return {
        "findings": finding_rows,
        "clusters": cluster_rows,
        "similarities": [
            item.to_dict()
            for item in similarities
            if item.score >= threshold
        ],
        "summary": {
            "findings": len(finding_rows),
            "clusters": len(cluster_rows),
            "report_review_ready_findings": sum(
                bool(row["readiness"])
                and row["readiness"]["readiness"] == "report_review_ready"
                for row in finding_rows
            ),
            "needs_validation_findings": sum(
                bool(row["readiness"])
                and row["readiness"]["readiness"] == "needs_validation"
                for row in finding_rows
            ),
            "blocked_findings": sum(
                bool(row["readiness"])
                and row["readiness"]["readiness"] == "blocked"
                for row in finding_rows
            ),
            "strong_differential_findings": sum(
                row["differential"]["signal"] == "strong"
                for row in finding_rows
            ),
            "weak_differential_findings": sum(
                row["differential"]["signal"] == "weak"
                for row in finding_rows
            ),
            "saturated_clusters": sum(
                bool(row["saturation"]) and row["saturation"]["saturated"]
                for row in cluster_rows
            ),
            "validations_saved": sum(
                row["saturation"]["validations_saved"]
                if row["saturation"] else 0
                for row in cluster_rows
            ),
        },
    }


@router.get("/api/campaigns/{campaign_id}/finding-intelligence")
def campaign_finding_intelligence(campaign_id: str, threshold: float = 0.75):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    store = storage()
    graph = load_observation_graph(store, campaign.id)
    snapshots = store.list_hypothesis_snapshots(campaign.id, limit=50)
    payload = build_finding_intelligence(
        campaign.findings,
        graph,
        hypothesis_snapshots=snapshots,
        threshold=threshold,
    )
    return {
        "campaign_id": campaign.id,
        "threshold": threshold,
        **payload,
        "read_only": True,
        "advisory_only": True,
        "auto_merge": False,
        "does_not_confirm_findings": True,
    }
