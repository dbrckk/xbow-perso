from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationState:
    finding_ids: frozenset[str]
    attempted_finding_ids: frozenset[str]
    observed_independent_finding_ids: frozenset[str]
    evidence_backed_independent_finding_ids: frozenset[str]

    @property
    def unresolved_finding_ids(self) -> frozenset[str]:
        return self.finding_ids - self.observed_independent_finding_ids

    @property
    def unattempted_finding_ids(self) -> frozenset[str]:
        return self.unresolved_finding_ids - self.attempted_finding_ids

    @property
    def unevidenced_finding_ids(self) -> frozenset[str]:
        return (
            self.observed_independent_finding_ids
            - self.evidence_backed_independent_finding_ids
        )

    @property
    def all_observed_independently(self) -> bool:
        return bool(self.finding_ids) and not self.unresolved_finding_ids

    @property
    def all_evidence_backed_independently(self) -> bool:
        return bool(self.finding_ids) and (
            self.finding_ids == self.evidence_backed_independent_finding_ids
        )


def analyze_validation_state(graph: Any) -> ValidationState:
    """Compute finding validation state once from an observation graph.

    Evidence-backed validation requires an independent observed validation node
    with at least one evidence observation directly attached to that validation.
    """
    finding_by_id = {item.id: item for item in graph.by_kind("finding")}
    evidence_parent_ids = {
        parent_id
        for evidence in graph.by_kind("evidence")
        for parent_id in evidence.parent_ids
    }
    attempted: set[str] = set()
    observed_independent: set[str] = set()
    evidence_backed_independent: set[str] = set()

    for validation in graph.by_kind("validation"):
        for parent_id in validation.parent_ids:
            finding = finding_by_id.get(parent_id)
            if finding is None:
                continue
            attempted.add(parent_id)
            if validation.value == "observed" and validation.source != finding.source:
                observed_independent.add(parent_id)
                if validation.id in evidence_parent_ids:
                    evidence_backed_independent.add(parent_id)

    return ValidationState(
        finding_ids=frozenset(finding_by_id),
        attempted_finding_ids=frozenset(attempted),
        observed_independent_finding_ids=frozenset(observed_independent),
        evidence_backed_independent_finding_ids=frozenset(
            evidence_backed_independent
        ),
    )


def observed_independent_finding_ids(graph: Any) -> set[str]:
    """Return finding observation IDs backed by independent observed validation."""
    return set(analyze_validation_state(graph).observed_independent_finding_ids)


def evidence_backed_independent_finding_ids(graph: Any) -> set[str]:
    """Return findings whose independent observed validation has child evidence."""
    return set(
        analyze_validation_state(graph).evidence_backed_independent_finding_ids
    )


def attempted_finding_ids(graph: Any) -> set[str]:
    """Return finding observation IDs that have any validation attempt."""
    return set(analyze_validation_state(graph).attempted_finding_ids)


def has_observed_independent_validation(graph: Any, finding_id: str) -> bool:
    return finding_id in analyze_validation_state(graph).observed_independent_finding_ids


def has_evidence_backed_independent_validation(graph: Any, finding_id: str) -> bool:
    return (
        finding_id
        in analyze_validation_state(graph).evidence_backed_independent_finding_ids
    )
