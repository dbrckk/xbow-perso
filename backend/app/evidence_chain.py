from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .finding_correlation import router as correlation_router
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import analyze_validation_state

router = APIRouter()
router.routes.extend(correlation_router.routes)


@dataclass(frozen=True)
class EvidenceChain:
    finding_id: str
    ancestor_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    independent_validation_observed: bool
    complete: bool
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ancestor_ids"] = list(self.ancestor_ids)
        payload["validation_ids"] = list(self.validation_ids)
        payload["evidence_ids"] = list(self.evidence_ids)
        payload["issues"] = list(self.issues)
        return payload


def _ancestors(graph: ObservationGraph, observation_id: str) -> tuple[str, ...]:
    by_id = {item.id: item for item in graph.values()}
    seen: set[str] = set()
    stack = list(by_id.get(observation_id).parent_ids if observation_id in by_id else ())
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        parent = by_id.get(current)
        if parent is not None:
            stack.extend(parent.parent_ids)
    return tuple(sorted(seen))


def build_evidence_chains(graph: ObservationGraph) -> list[EvidenceChain]:
    """Summarize support chains for findings without executing any target action."""
    validation_state = analyze_validation_state(graph)
    validations = graph.by_kind("validation")
    evidence = graph.by_kind("evidence")
    chains: list[EvidenceChain] = []

    for finding in graph.by_kind("finding"):
        validation_ids = tuple(
            sorted(item.id for item in validations if finding.id in item.parent_ids)
        )
        validation_id_set = set(validation_ids)
        evidence_ids = tuple(
            sorted(
                item.id
                for item in evidence
                if finding.id in item.parent_ids
                or any(parent in validation_id_set for parent in item.parent_ids)
            )
        )
        ancestors = _ancestors(graph, finding.id)
        independent = finding.id in validation_state.observed_independent_finding_ids

        issues = []
        if not ancestors:
            issues.append("missing_upstream_context")
        if not validation_ids:
            issues.append("missing_validation")
        if not independent:
            issues.append("missing_independent_observed_validation")
        if not evidence_ids:
            issues.append("missing_evidence")

        chains.append(
            EvidenceChain(
                finding_id=finding.id,
                ancestor_ids=ancestors,
                validation_ids=validation_ids,
                evidence_ids=evidence_ids,
                independent_validation_observed=independent,
                complete=not issues,
                issues=tuple(issues),
            )
        )

    return sorted(chains, key=lambda item: (item.complete, item.finding_id))


@router.get("/api/campaigns/{campaign_id}/evidence-chains")
def campaign_evidence_chains(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    chains = build_evidence_chains(graph)
    complete = sum(item.complete for item in chains)
    return {
        "campaign_id": campaign.id,
        "chains": [item.to_dict() for item in chains],
        "summary": {
            "total": len(chains),
            "complete": complete,
            "incomplete": len(chains) - complete,
        },
        "read_only": True,
    }
