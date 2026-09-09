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

    def add(self, observation: Observation) -> None:
        missing = [parent for parent in observation.parent_ids if parent not in self._observations]
        if missing:
            raise ValueError("observation references unknown parent")
        self._observations[observation.id] = observation

    def values(self) -> list[Observation]:
        return list(self._observations.values())

    def by_kind(self, kind: ObservationKind) -> list[Observation]:
        return [item for item in self._observations.values() if item.kind == kind]


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

        if not observations:
            return [PlannedAction("inventory", host, "no observations collected yet", 100)]
        if assets and not endpoints:
            return [PlannedAction("crawl", host, "known assets have no endpoint inventory", 90)]
        if endpoints and not findings:
            return [PlannedAction("scan", host, "endpoint inventory exists but no findings recorded", 80)]
        if findings and len(validations) < len(findings):
            return [PlannedAction("validate", host, "findings still require independent validation", 100)]
        if findings and len(validations) >= len(findings):
            return [PlannedAction("report", host, "all recorded findings have validation observations", 70)]
        return [PlannedAction("stop", host, "no bounded next action available", 10)]
