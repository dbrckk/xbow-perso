from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .evidence_chain import build_evidence_chains
from .finding_correlation import correlate_findings
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import analyze_validation_state

router = APIRouter()


@dataclass(frozen=True)
class FindingLifecycleAdvice:
    finding_id: str
    current_state: str
    recommended_state: str
    transition_allowed: bool
    prerequisites: tuple[str, ...]
    human_decision_required: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["prerequisites"] = list(self.prerequisites)
        return payload


def build_finding_lifecycle(findings: list[Any], graph: ObservationGraph) -> list[FindingLifecycleAdvice]:
    """Recommend conservative finding-state transitions from existing evidence.

    This is read-only advisory logic. It cannot mutate findings, execute target
    actions, approve reports, or submit reports.
    """
    validation = analyze_validation_state(graph)
    chains = {item.finding_id: item for item in build_evidence_chains(graph)}
    duplicate_ids = {
        finding_id
        for group in correlate_findings(findings)
        if group.duplicate_candidate
        for finding_id in group.finding_ids
    }

    advice: list[FindingLifecycleAdvice] = []
    for finding in findings:
        finding_id = str(finding.id)
        graph_id = f"finding:{finding_id}"
        current = str(finding.status)
        independent = graph_id in validation.observed_independent_finding_ids
        chain = chains.get(graph_id)
        chain_complete = bool(chain and chain.complete)
        duplicate = finding_id in duplicate_ids

        prerequisites: list[str] = []
        human_required = False

        if current == "candidate":
            recommended = "validation_required"
            allowed = True
        elif current == "validation_required":
            if not independent:
                prerequisites.append("independent_validation")
            if not chain_complete:
                prerequisites.append("complete_evidence_chain")
            if duplicate:
                prerequisites.append("duplicate_review")
            recommended = "human_confirm_or_reject"
            allowed = not prerequisites
            human_required = True
        elif current == "confirmed":
            if not independent:
                prerequisites.append("independent_validation")
            if not chain_complete:
                prerequisites.append("complete_evidence_chain")
            if duplicate:
                prerequisites.append("duplicate_review")
            recommended = "human_report_review"
            allowed = not prerequisites
            human_required = True
        elif current == "rejected":
            recommended = "terminal"
            allowed = False
        else:
            recommended = "hold"
            prerequisites.append("recognized_state")
            allowed = False

        advice.append(
            FindingLifecycleAdvice(
                finding_id=finding_id,
                current_state=current,
                recommended_state=recommended,
                transition_allowed=allowed,
                prerequisites=tuple(prerequisites),
                human_decision_required=human_required,
            )
        )

    return sorted(advice, key=lambda item: (item.finding_id, item.current_state))


@router.get("/api/campaigns/{campaign_id}/finding-lifecycle")
def campaign_finding_lifecycle(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    advice = build_finding_lifecycle(campaign.findings, graph)
    return {
        "campaign_id": campaign.id,
        "findings": [item.to_dict() for item in advice],
        "summary": {
            "total": len(advice),
            "transition_allowed": sum(item.transition_allowed for item in advice),
            "human_decision_required": sum(item.human_decision_required for item in advice),
        },
        "read_only": True,
        "advisory_only": True,
        "execution_authority": False,
    }
