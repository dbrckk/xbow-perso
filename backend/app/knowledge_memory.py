from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .observation_graph import ObservationGraph


@dataclass(frozen=True)
class FindingConfidence:
    finding_id: str
    score: float
    validation_count: int
    evidence_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeSnapshot:
    observations: int
    assets: int
    endpoints: int
    findings: int
    validations: int
    evidence: int
    finding_confidence: tuple[FindingConfidence, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["finding_confidence"] = [item.to_dict() for item in self.finding_confidence]
        return payload


def build_knowledge_snapshot(graph: ObservationGraph) -> KnowledgeSnapshot:
    assets = graph.by_kind("asset")
    endpoints = graph.by_kind("endpoint")
    findings = graph.by_kind("finding")
    validations = graph.by_kind("validation")
    evidence = graph.by_kind("evidence")

    scores: list[FindingConfidence] = []
    for finding in findings:
        linked_validations = [item for item in validations if finding.id in item.parent_ids]
        validation_ids = {item.id for item in linked_validations}
        linked_evidence = [
            item
            for item in evidence
            if any(parent in validation_ids or parent == finding.id for parent in item.parent_ids)
        ]
        score = 0.35
        if linked_validations:
            score += 0.40
        if linked_evidence:
            score += 0.20
        if any(item.metadata.get("artifact_kind") == "validation" for item in linked_evidence):
            score += 0.05
        scores.append(
            FindingConfidence(
                finding_id=finding.id,
                score=min(1.0, round(score, 2)),
                validation_count=len(linked_validations),
                evidence_count=len(linked_evidence),
            )
        )

    return KnowledgeSnapshot(
        observations=len(graph.values()),
        assets=len(assets),
        endpoints=len(endpoints),
        findings=len(findings),
        validations=len(validations),
        evidence=len(evidence),
        finding_confidence=tuple(scores),
    )


def decision_history(graph: ObservationGraph) -> list[dict[str, Any]]:
    history = []
    for item in graph.by_kind("evidence"):
        if item.metadata.get("memory_type") != "planner_decision":
            continue
        history.append(
            {
                "id": item.id,
                "action": item.metadata.get("action"),
                "agent": item.metadata.get("agent"),
                "reason": item.metadata.get("reason"),
                "priority": item.metadata.get("priority"),
                "graph_fingerprint": item.metadata.get("graph_fingerprint"),
            }
        )
    return history
