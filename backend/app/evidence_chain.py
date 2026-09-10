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
    source_count: int
    dangling_parent_ids: tuple[str, ...]
    cycle_detected: bool
    independent_validation_observed: bool
    complete: bool
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ancestor_ids"] = list(self.ancestor_ids)
        payload["validation_ids"] = list(self.validation_ids)
        payload["evidence_ids"] = list(self.evidence_ids)
        payload["dangling_parent_ids"] = list(self.dangling_parent_ids)
        payload["issues"] = list(self.issues)
        return payload


def _ancestry_integrity(
    graph: ObservationGraph,
    observation_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    by_id = {item.id: item for item in graph.values()}
    ancestors: set[str] = set()
    dangling: set[str] = set()
    cycle_detected = False

    def visit(current_id: str, path: tuple[str, ...]) -> None:
        nonlocal cycle_detected
        current = by_id.get(current_id)
        if current is None:
            dangling.add(current_id)
            return
        for parent_id in current.parent_ids:
            if parent_id in path or parent_id == observation_id:
                cycle_detected = True
                ancestors.add(parent_id)
                continue
            ancestors.add(parent_id)
            visit(parent_id, (*path, current_id))

    if observation_id in by_id:
        visit(observation_id, ())
    return tuple(sorted(ancestors)), tuple(sorted(dangling)), cycle_detected


def build_evidence_chains(graph: ObservationGraph) -> list[EvidenceChain]:
    """Summarize support-chain integrity for findings without target actions."""
    validation_state = analyze_validation_state(graph)
    validations = graph.by_kind("validation")
    evidence = graph.by_kind("evidence")
    by_id = {item.id: item for item in graph.values()}
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
        ancestors, dangling_parent_ids, cycle_detected = _ancestry_integrity(graph, finding.id)
        independent = finding.id in validation_state.observed_independent_finding_ids

        related_ids = {finding.id, *ancestors, *validation_ids, *evidence_ids}
        sources = {
            str(by_id[item_id].source)
            for item_id in related_ids
            if item_id in by_id and str(by_id[item_id].source).strip()
        }

        issues = []
        if not ancestors:
            issues.append("missing_upstream_context")
        if dangling_parent_ids:
            issues.append("dangling_parent_reference")
        if cycle_detected:
            issues.append("ancestry_cycle")
        if not validation_ids:
            issues.append("missing_validation")
        if not independent:
            issues.append("missing_independent_observed_validation")
        if not evidence_ids:
            issues.append("missing_evidence")
        if len(sources) < 2:
            issues.append("low_source_diversity")

        chains.append(
            EvidenceChain(
                finding_id=finding.id,
                ancestor_ids=ancestors,
                validation_ids=validation_ids,
                evidence_ids=evidence_ids,
                source_count=len(sources),
                dangling_parent_ids=dangling_parent_ids,
                cycle_detected=cycle_detected,
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
            "cycles": sum(item.cycle_detected for item in chains),
            "dangling_parent_references": sum(bool(item.dangling_parent_ids) for item in chains),
            "low_source_diversity": sum(item.source_count < 2 for item in chains),
        },
        "read_only": True,
    }
