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
        payload = asdict(self)
        payload["parent_ids"] = list(self.parent_ids)
        return payload


@dataclass(frozen=True)
class PlannedAction:
    kind: ActionKind
    target: str | None
    reason: str
    priority: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ObservationGraph:
    """Small deterministic observation graph used by the planner and tests."""

    def __init__(self) -> None:
        self._items: dict[str, Observation] = {}

    def add(self, observation: Observation) -> None:
        missing = [parent for parent in observation.parent_ids if parent not in self._items]
        if missing:
            raise ValueError(f"unknown parent observation(s): {', '.join(missing)}")
        existing = self._items.get(observation.id)
        if existing and existing != observation:
            raise ValueError(f"observation id already exists with different content: {observation.id}")
        self._items[observation.id] = observation

    @classmethod
    def from_records(cls, records: list[dict[str, Any]]) -> ObservationGraph:
        graph = cls()
        pending = [
            Observation(
                id=str(item["id"]),
                kind=item["kind"],
                value=str(item["value"]),
                source=str(item["source"]),
                parent_ids=tuple(item.get("parent_ids", ())),
                metadata=dict(item.get("metadata", {})),
            )
            for item in records
        ]
        while pending:
            remaining = []
            progressed = False
            for observation in pending:
                if all(parent in graph._items for parent in observation.parent_ids):
                    graph.add(observation)
                    progressed = True
                else:
                    remaining.append(observation)
            if not progressed:
                raise ValueError("observation records contain missing or cyclic parents")
            pending = remaining
        return graph

    def values(self) -> list[Observation]:
        return list(self._items.values())

    def by_kind(self, kind: ObservationKind) -> list[Observation]:
        return [item for item in self._items.values() if item.kind == kind]


def load_observation_graph(store: Any, campaign_id: str) -> ObservationGraph:
    """Load the durable observation graph for a campaign from storage."""
    return ObservationGraph.from_records(store.list_observations(campaign_id))


def _campaign_finding_id(observation: Observation) -> str:
    """Map canonical graph finding IDs to campaign IDs while preserving old fixtures."""
    prefix = "finding:"
    return observation.id[len(prefix) :] if observation.id.startswith(prefix) else observation.id


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

        campaign_findings = list(getattr(campaign, "findings", ()))
        if findings or campaign_findings:
            graph_finding_ids = {_campaign_finding_id(item) for item in findings}
            campaign_finding_ids = {str(item.id) for item in campaign_findings}
            if graph_finding_ids != campaign_finding_ids:
                return [
                    PlannedAction(
                        "stop",
                        host,
                        "observation graph and campaign finding state are inconsistent",
                        100,
                    )
                ]

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
            unresolved_findings = [
                item
                for item in campaign_findings
                if getattr(item, "status", None) not in {"confirmed", "rejected"}
            ]
            if unresolved_findings:
                return [
                    PlannedAction(
                        "stop",
                        host,
                        "observed findings await explicit confirmation or rejection",
                        100,
                    )
                ]

            confirmed_findings = [
                item for item in campaign_findings if getattr(item, "status", None) == "confirmed"
            ]
            if not confirmed_findings:
                return [PlannedAction("stop", host, "all findings rejected; no report required", 100)]

            report_exists = any(item.metadata.get("artifact_kind") == "report" for item in evidence)
            if report_exists:
                return [PlannedAction("stop", host, "report artifact already exists", 100)]
            return [PlannedAction("report", host, "confirmed findings are independently validated", 70)]

        if endpoints and not findings:
            scan_completed = any(
                item.metadata.get("phase") == "scan" and item.metadata.get("status") == "completed"
                for item in evidence
            )
            if scan_completed:
                return [PlannedAction("stop", host, "scan completed without recorded findings", 100)]
            return [PlannedAction("scan", host, "endpoint inventory exists but no findings recorded", 80)]

        if assets and not endpoints:
            return [PlannedAction("crawl", host, "asset inventory exists but endpoints are missing", 90)]

        return [PlannedAction("stop", host, "no safe planner transition available", 100)]
