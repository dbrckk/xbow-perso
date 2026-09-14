from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .evidence_quality import build_evidence_quality
from .finding_correlation import cluster_findings
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import observed_independent_finding_ids

router = APIRouter()


@dataclass(frozen=True)
class ClusterSaturation:
    cluster_id: str
    finding_ids: tuple[str, ...]
    cluster_confidence: float
    saturated: bool
    representative_finding_id: str | None
    validations_saved: int
    criteria: dict[str, bool]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["finding_ids"] = list(self.finding_ids)
        return payload


def build_cluster_saturation(
    findings: list[Any],
    graph: ObservationGraph,
    *,
    threshold: float = 0.75,
) -> list[ClusterSaturation]:
    clusters, _similarities = cluster_findings(findings, threshold=threshold)
    quality_by_id = {
        item.finding_id: item
        for item in build_evidence_quality(graph)
    }
    observed_validated = {
        item.removeprefix("finding:")
        for item in observed_independent_finding_ids(graph)
    }

    results: list[ClusterSaturation] = []
    for cluster in clusters:
        representative = None
        representative_quality = None
        for finding_id in cluster.finding_ids:
            quality = quality_by_id.get(finding_id)
            if finding_id in observed_validated and quality is not None:
                representative = finding_id
                representative_quality = quality
                if (
                    quality.grade == "high"
                    and quality.integrity_attested
                    and quality.corroborated
                ):
                    break

        criteria = {
            "cluster_confidence_gte_0_90": cluster.confidence >= 0.90,
            "representative_independently_observed": representative in observed_validated if representative else False,
            "evidence_quality_high": bool(representative_quality and representative_quality.grade == "high"),
            "artifact_integrity_attested": bool(representative_quality and representative_quality.integrity_attested),
            "independently_corroborated": bool(representative_quality and representative_quality.corroborated),
        }
        saturated = all(criteria.values())
        validations_saved = max(0, len(cluster.finding_ids) - 1) if saturated else 0
        reason = (
            "strong representative evidence saturates further automatic cluster validation"
            if saturated
            else "cluster does not meet all saturation criteria"
        )
        results.append(
            ClusterSaturation(
                cluster_id=cluster.cluster_id,
                finding_ids=cluster.finding_ids,
                cluster_confidence=cluster.confidence,
                saturated=saturated,
                representative_finding_id=representative,
                validations_saved=validations_saved,
                criteria=criteria,
                reason=reason,
            )
        )

    return sorted(
        results,
        key=lambda item: (
            not item.saturated,
            -item.cluster_confidence,
            item.cluster_id,
        ),
    )


@router.get("/api/campaigns/{campaign_id}/finding-cluster-saturation")
def campaign_finding_cluster_saturation(campaign_id: str, threshold: float = 0.75):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    saturation = build_cluster_saturation(
        campaign.findings,
        graph,
        threshold=threshold,
    )
    return {
        "campaign_id": campaign.id,
        "threshold": threshold,
        "clusters": [item.to_dict() for item in saturation],
        "summary": {
            "clusters": len(saturation),
            "saturated": sum(item.saturated for item in saturation),
            "validations_saved": sum(item.validations_saved for item in saturation),
        },
        "read_only": True,
        "advisory_only": True,
        "auto_merge": False,
    }
