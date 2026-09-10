from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .evidence_chain import build_evidence_chains
from .finding_correlation import correlate_findings
from .finding_lifecycle import router as finding_lifecycle_router
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import analyze_validation_state

router = APIRouter()
router.routes.extend(finding_lifecycle_router.routes)


@dataclass(frozen=True)
class ReportReadiness:
    finding_id: str
    score: float
    ready_for_human_review: bool
    confirmed: bool
    independent_validation_observed: bool
    evidence_chain_complete: bool
    duplicate_candidate: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


def build_report_readiness(
    findings: list[Any], graph: ObservationGraph
) -> list[ReportReadiness]:
    """Score report review readiness using existing evidence only.

    This layer is read-only and advisory. It cannot approve or submit reports.
    """
    validation = analyze_validation_state(graph)
    chains = {item.finding_id: item for item in build_evidence_chains(graph)}
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
        chain = chains.get(graph_id)
        chain_complete = bool(chain and chain.complete)
        duplicate = finding_id in duplicate_ids

        blockers: list[str] = []
        if not confirmed:
            blockers.append("finding_not_confirmed")
        if not independent:
            blockers.append("missing_independent_validation")
        if not chain_complete:
            blockers.append("incomplete_evidence_chain")
        if duplicate:
            blockers.append("duplicate_review_required")

        score = round(
            (0.25 if confirmed else 0.0)
            + (0.30 if independent else 0.0)
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
                evidence_chain_complete=chain_complete,
                duplicate_candidate=duplicate,
                blockers=tuple(blockers),
            )
        )

    return sorted(readiness, key=lambda item: (-item.score, item.finding_id))


@router.get("/api/campaigns/{campaign_id}/report-readiness")
def campaign_report_readiness(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    readiness = build_report_readiness(campaign.findings, graph)
    return {
        "campaign_id": campaign.id,
        "findings": [item.to_dict() for item in readiness],
        "summary": {
            "total": len(readiness),
            "ready_for_human_review": sum(item.ready_for_human_review for item in readiness),
            "blocked": sum(not item.ready_for_human_review for item in readiness),
            "highest_score": max((item.score for item in readiness), default=0.0),
        },
        "read_only": True,
        "advisory_only": True,
        "human_approval_required": True,
        "execution_authority": False,
    }
