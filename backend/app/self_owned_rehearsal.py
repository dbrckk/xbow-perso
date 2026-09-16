from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Iterable, Literal, Mapping

MANDATORY_SCENARIOS = (
    "redirect_scope_enforcement",
    "subdomain_scope_enforcement",
    "http_429_bounded",
    "worker_failure_durability",
    "crash_window_outbox_recovery",
    "cancellation_enforcement",
    "secret_sentinel_confinement",
    "scope_drift_blocks_execution",
)


@dataclass(frozen=True)
class ScenarioReferences:
    campaign_id: str | None = None
    job_ids: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    counters: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    status: Literal["pass", "fail"]
    reason: str
    references: ScenarioReferences = field(default_factory=ScenarioReferences)
    external_network_used: bool = False
    contains_secrets: bool = False


@dataclass(frozen=True)
class RehearsalReport:
    status: Literal["pass", "fail"]
    scenarios: tuple[ScenarioResult, ...]
    external_network_used: bool
    contains_secrets: bool


def contains_raw_value(value: str, surfaces: Iterable[object]) -> bool:
    if not value:
        return False
    needle = value.encode("utf-8")
    for surface in surfaces:
        encoded = (
            surface
            if isinstance(surface, bytes)
            else json.dumps(surface, ensure_ascii=False, default=str).encode("utf-8")
        )
        if needle in encoded:
            return True
    return False


def run_rehearsal(
    scenarios: Mapping[str, Callable[[], ScenarioResult]],
) -> RehearsalReport:
    results: list[ScenarioResult] = []
    for name in MANDATORY_SCENARIOS:
        runner = scenarios.get(name)
        if runner is None:
            results.append(
                ScenarioResult(name=name, status="fail", reason="scenario_missing")
            )
            continue
        try:
            result = runner()
        except Exception as exc:
            result = ScenarioResult(
                name=name,
                status="fail",
                reason=f"unexpected_{exc.__class__.__name__}",
            )
        if result.name != name:
            result = ScenarioResult(
                name=name,
                status="fail",
                reason="scenario_name_mismatch",
            )
        results.append(result)
    external = any(item.external_network_used for item in results)
    secrets = any(item.contains_secrets for item in results)
    failed = external or secrets or any(item.status != "pass" for item in results)
    return RehearsalReport(
        status="fail" if failed else "pass",
        scenarios=tuple(results),
        external_network_used=external,
        contains_secrets=secrets,
    )
