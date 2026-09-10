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
class FindingPriority:
    finding_id: str
    score: float
    severity_weight: float
    confidence: float

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


def _validation_quality(value: str) -> float:
    """Return bounded confidence credit for a validator outcome.

    A dry run proves policy/plumbing only, an error proves nothing about the target,
    and an observed response is useful evidence without self-confirming a finding.
    Unknown outcomes fail closed and receive no validation credit.
    """
    return {
        "observed": 0.40,
        "dry_run": 0.05,
        "error": 0.0,
    }.get(str(value), 0.0)


def build_knowledge_snapshot(graph: ObservationGraph) -> KnowledgeSnapshot:
    assets = graph.by_kind("asset")
    endpoints = graph.by_kind("endpoint")
    findings = graph.by_kind("finding")
    validations = graph.by_kind("validation")
    evidence = graph.by_kind("evidence")

    scores: list[FindingConfidence] = []
    for finding in findings:
        linked_validations = [item for item in validations if finding.id in item.parent_ids]
        independent_validations = [item for item in linked_validations if item.source != finding.source]
        credited_validations = [
            item for item in independent_validations if _validation_quality(item.value) > 0.0
        ]
        credited_validation_ids = {item.id for item in credited_validations}
        observed_validation_ids = {
            item.id for item in independent_validations if _validation_quality(item.value) >= 0.40
        }
        observed_evidence = [
            item
            for item in evidence
            if any(parent in observed_validation_ids for parent in item.parent_ids)
        ]

        best_validation_credit = max(
            (_validation_quality(item.value) for item in independent_validations),
            default=0.0,
        )
        score = 0.35 + best_validation_credit
        if observed_evidence:
            score += 0.20
        if any(item.metadata.get("artifact_kind") == "validation" for item in observed_evidence):
            score += 0.05
        scores.append(
            FindingConfidence(
                finding_id=finding.id,
                score=min(1.0, round(score, 2)),
                validation_count=len(credited_validations),
                evidence_count=len(observed_evidence),
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


def rank_findings(findings: list[Any], graph: ObservationGraph) -> list[FindingPriority]:
    """Rank findings for independent validation using impact and evidence gaps.

    Higher severity raises priority while stronger existing evidence lowers the
    urgency for another validation pass. Ties are deterministic by finding id.
    """
    severity_weights = {
        "info": 0.10,
        "low": 0.25,
        "medium": 0.50,
        "high": 0.75,
        "critical": 1.00,
    }
    confidence = {
        item.finding_id: item.score
        for item in build_knowledge_snapshot(graph).finding_confidence
    }
    ranked = []
    for finding in findings:
        finding_id = f"finding:{finding.id}"
        confidence_score = confidence.get(finding_id, 0.0)
        severity_weight = severity_weights.get(str(finding.severity), 0.0)
        score = round((severity_weight * 0.70) + ((1.0 - confidence_score) * 0.30), 4)
        ranked.append(
            FindingPriority(
                finding_id=str(finding.id),
                score=score,
                severity_weight=severity_weight,
                confidence=confidence_score,
            )
        )
    return sorted(ranked, key=lambda item: (-item.score, item.finding_id))


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
