from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .cve_evidence_verdict import build_cve_evidence_verdict
from .cve_risk_context import build_cve_risk_context
from .cve_validation_priority import build_cve_validation_plan
from .differential_intelligence import DifferentialSignal, build_differential_signals
from .finding_cluster_consensus import build_cluster_consensus
from .finding_cluster_saturation import build_cluster_saturation
from .finding_correlation import cluster_findings
from .finding_readiness import build_finding_readiness
from .finding_triage import build_finding_triage
from .observation_graph import load_observation_graph
from .public_duplicate_intelligence import rank_public_duplicate_risk
from .technology_fingerprint_intelligence import (
    build_technology_fingerprints,
    match_finding_technology,
)
from .validation_priority import build_validation_priority
from .vulnerability_intelligence import build_vulnerability_signal

router = APIRouter()


def build_finding_intelligence(
    findings: list[Any],
    graph: Any,
    *,
    hypothesis_snapshots: list[dict[str, Any]] | None = None,
    threshold: float = 0.75,
    public_reports: list[dict[str, Any]] | None = None,
    program_handle: str | None = None,
    kev_catalog: Any | None = None,
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
    technology_fingerprints = build_technology_fingerprints(graph)

    readiness_by_id = {item.finding_id: item for item in readiness}
    triage_by_id = {item.finding_id: item for item in triage}
    cluster_by_member = {
        finding_id: cluster
        for cluster in clusters
        for finding_id in cluster.finding_ids
    }
    consensus_by_cluster = {item.cluster_id: item for item in cluster_consensus}
    saturation_by_cluster = {item.cluster_id: item for item in saturation}
    finding_by_id = {str(item.id): item for item in findings}

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
        duplicate_similarity = rank_public_duplicate_risk(
            finding,
            list(public_reports or []),
            program_handle=program_handle,
        )

        member_ids = cluster.finding_ids if cluster else (finding_id,)
        corroborating_sources = {
            str(getattr(finding_by_id.get(member_id), "discovered_by", "") or "").strip()
            for member_id in member_ids
            if member_id in finding_by_id
        }
        matched_fingerprints = match_finding_technology(
            finding,
            technology_fingerprints,
        )
        versioned_fingerprint_match_count = sum(
            item.version is not None for item in matched_fingerprints
        )
        high_confidence_fingerprint_match_count = sum(
            item.version is not None and item.confidence >= 0.75
            for item in matched_fingerprints
        )
        vulnerability = build_vulnerability_signal(
            finding,
            differential_signal=differential_item.signal,
            corroborating_sources=corroborating_sources,
            versioned_fingerprint_match_count=versioned_fingerprint_match_count,
            high_confidence_fingerprint_match_count=(
                high_confidence_fingerprint_match_count
            ),
        )
        cve_evidence_verdict = build_cve_evidence_verdict(
            finding,
            differential_signal=differential_item.signal,
            versioned_fingerprint_match_count=versioned_fingerprint_match_count,
            high_confidence_fingerprint_match_count=(
                high_confidence_fingerprint_match_count
            ),
        )
        cve_risk_context = build_cve_risk_context(
            finding,
            kev_catalog=kev_catalog,
        )
        cve_validation_plan = build_cve_validation_plan(
            finding,
            verdict=cve_evidence_verdict,
        )
        cluster_saturated = bool(
            cluster_id in saturation_by_cluster
            and saturation_by_cluster[cluster_id].saturated
        )
        validation_priority = build_validation_priority(
            finding,
            cve_verdict=cve_evidence_verdict,
            vulnerability_signal=vulnerability,
            differential_signal=differential_item.signal,
            triage_score=(triage_item.score if triage_item else 0.0),
            cve_risk_score=cve_risk_context.risk_score,
            duplicate_candidate=bool(
                triage_item and triage_item.duplicate_candidate
            ),
            cluster_saturated=cluster_saturated,
        )

        finding_rows.append(
            {
                "finding_id": finding_id,
                "severity": str(getattr(finding, "severity", "")),
                "status": str(getattr(finding, "status", "")),
                "readiness": readiness_item.to_dict() if readiness_item else None,
                "triage": triage_item.to_dict() if triage_item else None,
                "differential": differential_item.to_dict(),
                "vulnerability": vulnerability.to_dict(),
                "cve_evidence_verdict": cve_evidence_verdict.to_dict(),
                "cve_risk_context": cve_risk_context.to_dict(),
                "cve_validation_plan": cve_validation_plan.to_dict(),
                "validation_priority": validation_priority.to_dict(),
                "technology": {
                    "matched_fingerprints": [
                        item.to_dict() for item in matched_fingerprints
                    ],
                    "versioned_match_count": versioned_fingerprint_match_count,
                    "high_confidence_match_count": (
                        high_confidence_fingerprint_match_count
                    ),
                },
                "public_duplicate_similarity": duplicate_similarity,
                "cluster_id": cluster_id,
                "cluster_status": (
                    consensus_by_cluster[cluster_id].status
                    if cluster_id in consensus_by_cluster
                    else None
                ),
                "cluster_saturated": cluster_saturated,
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
            "known_cve_candidates": sum(
                row["vulnerability"]["known_cve_candidate"]
                for row in finding_rows
            ),
            "multi_scanner_cve_candidates": sum(
                row["vulnerability"]["cve_signal"]
                == "multi_scanner_cve_candidate"
                for row in finding_rows
            ),
            "version_correlated_cve_candidates": sum(
                row["vulnerability"]["version_correlated"]
                for row in finding_rows
            ),
            "high_confidence_version_correlated_cve_candidates": sum(
                row["vulnerability"]["high_confidence_fingerprint_match_count"] > 0
                and row["vulnerability"]["known_cve_candidate"]
                for row in finding_rows
            ),
            "high_priority_cve_contexts": sum(
                row["cve_risk_context"]["risk_band"]
                in {"high_priority", "critical_priority"}
                for row in finding_rows
            ),
            "scanner_tagged_kev_unverified": sum(
                row["cve_risk_context"]["scanner_tagged_kev"]
                and not row["cve_risk_context"]["authoritative_kev_verified"]
                for row in finding_rows
            ),
            "authoritative_kev_candidates": sum(
                row["cve_risk_context"]["authoritative_kev_verified"]
                for row in finding_rows
            ),
            "novel_candidates": sum(
                row["vulnerability"]["novel_candidate"]
                for row in finding_rows
            ),
            "novel_candidates_needing_corroboration": sum(
                row["vulnerability"]["novelty_signal"]
                == "behavioral_candidate_needs_corroboration"
                for row in finding_rows
            ),
            "urgent_validation_candidates": sum(
                row["validation_priority"]["band"] == "urgent"
                for row in finding_rows
            ),
            "safe_active_validation_candidates": sum(
                row["validation_priority"]["recommended_state"]
                == "safe_active_validation"
                for row in finding_rows
            ),
            "passive_review_candidates": sum(
                row["validation_priority"]["recommended_state"]
                == "passive_review"
                for row in finding_rows
            ),
            "deferred_duplicate_validations": sum(
                row["validation_priority"]["recommended_state"]
                == "defer_duplicate_validation"
                for row in finding_rows
            ),
            "high_public_similarity_findings": sum(
                row["public_duplicate_similarity"]["similarity_band"]
                == "high_public_similarity"
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
    intelligence = store.get_hackerone_intelligence_state() or {}
    public_reports = (
        list(intelligence.get("reports") or [])
        if isinstance(intelligence, dict)
        else []
    )
    program_handle = None
    for event in reversed(campaign.events):
        if event.get("type") != "hackerone_policy_bound":
            continue
        binding = event.get("remote_binding")
        if isinstance(binding, dict) and binding.get("verified") is True:
            handle = str(binding.get("handle") or "").strip()
            if handle:
                program_handle = handle
        break

    payload = build_finding_intelligence(
        campaign.findings,
        graph,
        hypothesis_snapshots=snapshots,
        threshold=threshold,
        public_reports=public_reports,
        program_handle=program_handle,
    )
    return {
        "campaign_id": campaign.id,
        "threshold": threshold,
        **payload,
        "read_only": True,
        "advisory_only": True,
        "auto_merge": False,
        "does_not_confirm_findings": True,
        "does_not_claim_zero_day": True,
    }
