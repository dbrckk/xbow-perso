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
    relevant_ids = {item.id for item in graph.by_kind("finding")}
    relevant_ids.update(
        item.id
        for item in graph.by_kind("validation")
        if any(parent in relevant_ids for parent in item.parent_ids)
    )
    relevant_ids.update(
        item.id
        for item in graph.by_kind("evidence")
        if any(parent in relevant_ids for parent in item.parent_ids)
    )
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
        if item.id in relevant_ids
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


def diff_hypothesis_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any]:
    previous_items = {
        str(item.get("finding_id")): item
        for item in (previous or {}).get("hypotheses", [])
        if item.get("finding_id") is not None
    }
    current_items = {
        str(item.get("finding_id")): item
        for item in (current or {}).get("hypotheses", [])
        if item.get("finding_id") is not None
    }

    changes = []
    for finding_id in sorted(set(previous_items) | set(current_items)):
        before = previous_items.get(finding_id)
        after = current_items.get(finding_id)

        if before is None:
            changes.append(
                {
                    "finding_id": finding_id,
                    "change": "added",
                    "before": None,
                    "after": after,
                }
            )
            continue
        if after is None:
            changes.append(
                {
                    "finding_id": finding_id,
                    "change": "removed",
                    "before": before,
                    "after": None,
                }
            )
            continue

        before_evidence = set(before.get("evidence_ids", []))
        after_evidence = set(after.get("evidence_ids", []))
        confidence_before = float(before.get("confidence", 0.0))
        confidence_after = float(after.get("confidence", 0.0))
        status_before = str(before.get("status", ""))
        status_after = str(after.get("status", ""))

        evidence_added = sorted(after_evidence - before_evidence)
        evidence_removed = sorted(before_evidence - after_evidence)
        confidence_delta = round(confidence_after - confidence_before, 4)

        if (
            confidence_delta == 0.0
            and status_before == status_after
            and not evidence_added
            and not evidence_removed
        ):
            continue

        changes.append(
            {
                "finding_id": finding_id,
                "change": "updated",
                "confidence_before": confidence_before,
                "confidence_after": confidence_after,
                "confidence_delta": confidence_delta,
                "status_before": status_before,
                "status_after": status_after,
                "evidence_added": evidence_added,
                "evidence_removed": evidence_removed,
            }
        )

    return {
        "from_fingerprint": (previous or {}).get("graph_fingerprint"),
        "to_fingerprint": (current or {}).get("graph_fingerprint"),
        "changes": changes,
        "changed": bool(changes),
    }
