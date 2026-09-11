from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .observation_graph import ObservationGraph


@dataclass(frozen=True)
class Hypothesis:
    id: str
    finding_id: str
    statement: str
    confidence: float
    status: str
    graph_fingerprint: str
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_ids"] = list(self.evidence_ids)
        return payload


def hypothesis_graph_fingerprint(graph: ObservationGraph) -> str:
    payload = [
        {
            "id": item.id,
            "kind": item.kind,
            "value": item.value,
            "source": item.source,
            "parent_ids": list(item.parent_ids),
            "metadata": item.metadata,
        }
        for item in sorted(graph.values(), key=lambda item: item.id)
        if item.metadata.get("memory_type") != "planner_decision"
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def hypothesis_snapshot_is_current(hypothesis: Hypothesis, graph: ObservationGraph) -> bool:
    return hypothesis.graph_fingerprint == hypothesis_graph_fingerprint(graph)


def build_hypotheses(graph: ObservationGraph) -> list[Hypothesis]:
    """Build deterministic, read-only hypotheses from recorded findings.

    Hypotheses never authorize execution. They summarize evidence gaps for the
    bounded planner and preserve the existing policy/validation boundary.
    """
    fingerprint = hypothesis_graph_fingerprint(graph)
    validations = graph.by_kind("validation")
    evidence = graph.by_kind("evidence")
    result: list[Hypothesis] = []

    for finding in graph.by_kind("finding"):
        linked_validations = [
            item for item in validations
            if finding.id in item.parent_ids and item.source != finding.source
        ]
        validation_ids = {item.id for item in linked_validations}
        linked_evidence = [
            item for item in evidence
            if any(parent in validation_ids for parent in item.parent_ids)
        ]
        observed = any(item.value == "observed" for item in linked_validations)
        confidence = 0.35 + (0.40 if observed else 0.0) + (0.20 if linked_evidence else 0.0)
        status = "supported" if observed and linked_evidence else (
            "partially_supported" if linked_validations else "unvalidated"
        )
        result.append(
            Hypothesis(
                id=f"hypothesis:{finding.id}",
                finding_id=finding.id.removeprefix("finding:"),
                statement=f"Recorded finding {finding.value} requires independent evidence correlation.",
                confidence=min(0.95, round(confidence, 2)),
                status=status,
                graph_fingerprint=fingerprint,
                evidence_ids=tuple(sorted(item.id for item in linked_evidence)),
            )
        )

    return sorted(result, key=lambda item: (-item.confidence, item.id))
