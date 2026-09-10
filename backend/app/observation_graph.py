from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

ObservationKind = Literal["asset", "endpoint", "technology", "finding", "evidence", "validation"]
ActionKind = Literal["inventory", "crawl", "scan", "validate", "report", "stop"]


@dataclass(frozen=True)
class Observation:
    id: str
    kind: ObservationKind
    value: str
    source: str
    parent_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlannedAction:
    kind: ActionKind
    target: str | None
    reason: str
    priority: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ObservationGraph:
    """Small deterministic graph used by the planner; it never executes network actions."""

    def __init__(self) -> None:
        self._observations: dict[str, Observation] = {}

    @classmethod
    def from_records(cls, records: list[dict[str, Any]]) -> ObservationGraph:
        """Rebuild a graph from durable records without relying on database row order."""
        graph = cls()
        pending = {
            str(record["id"]): Observation(
                id=str(record["id"]),
                kind=record["kind"],
                value=str(record["value"]),
                source=str(record["source"]),
                parent_ids=tuple(str(item) for item in record.get("parent_ids", ())),
                metadata=dict(record.get("metadata", {})),
            )
            for record in records
        }
        while pending:
            progressed = False
            for observation_id, observation in list(pending.items()):
                if all(parent in graph._observations for parent in observation.parent_ids):
                    graph.add(observation)
                    pending.pop(observation_id)
                    progressed = True
            if not progressed:
                raise ValueError("persisted observation graph has missing or cyclic parents")
        return graph

    def add(self, observation: Observation) -> None:
        missing = [parent for parent in observation.parent_ids if parent not in self._observations]
        if missing:
            raise ValueError("observation references unknown parent")
        self._observations[observation.id] = observation

    def values(self) -> list[Observation]:
        return list(self._observations.values())

    def by_kind(self, kind: ObservationKind) -> list[Observation]:
        return [item for item in self._observations.values() if item.kind == kind]


def load_observation_graph(store: Any, campaign_id: str) -> ObservationGraph:
    """Load the durable observation graph for a campaign from storage."""
    return ObservationGraph.from_records(store.list_observations(campaign_id))


class AdaptivePlanner:
    """Deterministic, bounded decision layer for authorized campaign progression."""

    def plan(self, campaign: Any, graph: ObservationGraph) -> list[PlannedAction]:
        target = str(campaign.target.primary_url)
        host = (urlparse(target).hostname or "").lower()
        if not host:
            return [PlannedAction("stop", None, "target has no hostname", 100)]

        rules = campaign.target.rules
        if not rules.automated_scanning:
            return [PlannedAction("stop", host, "automated scanning disabled by program rules", 100)]

        observations = graph.values()
        assets = graph.by_kind("asset")
        endpoints = graph.by_kind("endpoint")
        findings = graph.by_kind("finding")
        validations = graph.by_kind("validation")
        evidence = graph.by_kind("evidence")

        if not observations:
            return [PlannedAction("inventory", host, "no observations collected yet", 100)]

        finding_by_id = {item.id: item for item in findings}
        attempted_finding_ids = {
            parent_id
            for validation in validations
            for parent_id in validation.parent_ids
            if parent_id in finding_by_id
        }
        observed_validated_finding_ids = {
            parent_id
            for validation in validations
            if validation.value == "observed"
            for parent_id in validation.parent_ids
            if parent_id in finding_by_id and validation.source != finding_by_id[parent_id].source
        }
        if findings and len(observed_validated_finding_ids) < len(findings):
            unresolved = set(finding_by_id) - observed_validated_finding_ids
            unattempted = unresolved - attempted_finding_ids
            if unattempted:
                return [PlannedAction("validate", host, "findings still require independent validation", 100)]
            return [
                PlannedAction(
                    "stop",
                    host,
                    "independent validation did not produce observed evidence for all findings",
                    100,
                )
            ]

        if findings and len(observed_validated_finding_ids) >= len(findings):
            report_exists = any(item.metadata.get("artifact_kind") == "report" for item in evidence)
            if report_exists:
                return [PlannedAction("stop", host, "validated findings already have a generated report", 100)]
            return [PlannedAction("report", host, "all recorded findings have observed independent validation", 70)]

        if assets and not endpoints:
            return [PlannedAction("crawl", host, "known assets have no endpoint inventory", 90)]
        if endpoints and not findings:
            scan_completed = any(
                item.metadata.get("phase") == "scan" and item.metadata.get("status") == "completed"
                for item in evidence
            )
            if scan_completed:
                return [PlannedAction("stop", host, "scan completed without recorded findings", 100)]
            return [PlannedAction("scan", host, "endpoint inventory exists but no findings recorded", 80)]
        return [PlannedAction("stop", host, "no bounded next action available", 10)]
