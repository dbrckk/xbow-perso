from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .evidence_chain import build_evidence_chains
from .evidence_quality import build_evidence_quality
from .finding_consensus import build_finding_consensus
from .finding_correlation import correlate_findings
from .observation_graph import ObservationGraph, load_observation_graph
from .report_provenance import verify_report_provenance
from .validation_state import analyze_validation_state

router = APIRouter()

_CWE_RE = re.compile(r"^CWE-[1-9][0-9]{0,5}$")


@dataclass(frozen=True)
class ReportReadiness:
    finding_id: str
    score: float
    ready_for_human_review: bool
    confirmed: bool
    independent_validation_observed: bool
    evidence_backed_independent_validation: bool
    consensus_level: str
    evidence_chain_complete: bool
    duplicate_candidate: bool
    blockers: tuple[str, ...]
    submission_ready: bool
    submission_completeness_score: float
    evidence_quality_grade: str
    metadata_blockers: tuple[str, ...]
    metadata_checks: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["metadata_blockers"] = list(self.metadata_blockers)
        return payload


def build_report_readiness(
    findings: list[Any], graph: ObservationGraph
) -> list[ReportReadiness]:
    """Score report review readiness using existing evidence only.

    This layer is read-only and advisory. It cannot approve or submit reports.
    """
    validation = analyze_validation_state(graph)
    chains = {item.finding_id: item for item in build_evidence_chains(graph)}
    quality_by_id = {
        item.finding_id: item
        for item in build_evidence_quality(graph)
    }
    consensus_by_id = {
        item.finding_id: item
        for item in build_finding_consensus(graph)
    }
    duplicate_ids = {
        finding_id
        for group in correlate_findings(findings)
        if group.duplicate_candidate
        for finding_id in group.finding_ids
    }

    readiness: list[ReportReadiness] = []
    for finding in findings:
        finding_id = str(finding.id)
        graph_id = f"finding:{finding_id}"
        confirmed = str(finding.status) == "confirmed"
        independent = graph_id in validation.observed_independent_finding_ids
        evidence_backed = graph_id in validation.evidence_backed_independent_finding_ids
        consensus = consensus_by_id.get(finding_id)
        consensus_level = str(consensus.consensus_level if consensus else "none")
        chain = chains.get(graph_id)
        chain_complete = bool(chain and chain.complete)
        duplicate = finding_id in duplicate_ids

        blockers: list[str] = []
        if not confirmed:
            blockers.append("finding_not_confirmed")
        if not independent:
            blockers.append("missing_independent_validation")
        if independent and not evidence_backed:
            blockers.append("missing_evidence_backed_independent_validation")
        if not chain_complete:
            blockers.append("incomplete_evidence_chain")
        if duplicate:
            blockers.append("duplicate_review_required")

        quality = quality_by_id.get(finding_id)
        evidence_grade = str(quality.grade if quality else "low")
        cwe = str(getattr(finding, "cwe", "") or "").strip().upper()
        cvss = getattr(finding, "cvss", None)
        metadata_checks = {
            "summary_present": bool(str(getattr(finding, "summary", "") or "").strip()),
            "impact_present": bool(str(getattr(finding, "impact", "") or "").strip()),
            "reproduction_steps_present": bool(getattr(finding, "reproduction_steps", None)),
            "remediation_present": bool(str(getattr(finding, "remediation", "") or "").strip()),
            "cwe_valid": bool(_CWE_RE.fullmatch(cwe)),
            "cvss_present": isinstance(cvss, (int, float)) and 0.0 <= float(cvss) <= 10.0,
            "evidence_high_quality": bool(
                quality and quality.grade == "high" and float(quality.score) >= 0.80
            ),
        }
        metadata_blockers = tuple(
            name for name, passed in metadata_checks.items() if not passed
        )
        completeness = round(
            sum(metadata_checks.values()) / len(metadata_checks),
            4,
        )

        score = round(
            (0.25 if confirmed else 0.0)
            + (0.30 if evidence_backed else 0.0)
            + (0.30 if chain_complete else 0.0)
            + (0.15 if not duplicate else 0.0),
            4,
        )
        readiness.append(
            ReportReadiness(
                finding_id=finding_id,
                score=score,
                ready_for_human_review=not blockers,
                confirmed=confirmed,
                independent_validation_observed=independent,
                evidence_backed_independent_validation=evidence_backed,
                consensus_level=consensus_level,
                evidence_chain_complete=chain_complete,
                duplicate_candidate=duplicate,
                blockers=tuple(blockers),
                submission_ready=not blockers and not metadata_blockers,
                submission_completeness_score=completeness,
                evidence_quality_grade=evidence_grade,
                metadata_blockers=metadata_blockers,
                metadata_checks=metadata_checks,
            )
        )

    return sorted(readiness, key=lambda item: (-item.score, item.finding_id))


@router.get("/api/campaigns/{campaign_id}/report-readiness")
def campaign_report_readiness(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    from .report_quality import summarize_report_quality
    from .reporting_governance import build_reporting_governance_snapshot

    reporting = build_reporting_governance_snapshot(
        campaign.findings,
        graph,
    )
    readiness = list(reporting.readiness)
    provenance = list(reporting.provenance)
    quality_gates = list(reporting.quality_gates)
    return {
        "campaign_id": campaign.id,
        "findings": [item.to_dict() for item in readiness],
        "provenance": {
            "schema": "report-provenance-v1",
            "findings": [
                {
                    **item.to_dict(),
                    "verification": verify_report_provenance(item),
                }
                for item in provenance
            ],
            "summary": {
                "total": len(provenance),
                "complete": sum(item.complete for item in provenance),
                "blocked": sum(not item.complete for item in provenance),
                "aggregate_fingerprint": reporting.provenance_fingerprint,
            },
            "read_only": True,
            "advisory_only": True,
        },
        "quality": {
            "findings": [item.to_dict() for item in quality_gates],
            "summary": summarize_report_quality(quality_gates),
        },
        "summary": {
            "total": len(readiness),
            "ready_for_human_review": sum(item.ready_for_human_review for item in readiness),
            "blocked": sum(not item.ready_for_human_review for item in readiness),
            "evidence_backed_validations": sum(
                item.evidence_backed_independent_validation for item in readiness
            ),
            "consensus_quorum": sum(
                item.consensus_level == "quorum" for item in readiness
            ),
            "highest_score": max((item.score for item in readiness), default=0.0),
            "submission_ready": sum(item.submission_ready for item in readiness),
            "submission_blocked": sum(not item.submission_ready for item in readiness),
            "average_submission_completeness": round(
                sum(item.submission_completeness_score for item in readiness) / len(readiness),
                4,
            )
            if readiness
            else 0.0,
        },
        "read_only": True,
        "advisory_only": True,
        "human_approval_required": True,
        "execution_authority": False,
    }
