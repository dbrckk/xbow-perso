from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .jobqueue import JobQueue
from .knowledge_memory import decision_history
from .observation_graph import ObservationGraph, PlannedAction


@dataclass(frozen=True)
class PlannerBudget:
    max_actions: int = 50
    max_scans: int = 3
    max_validations: int = 25
    max_validation_batch: int = 10
    max_reports: int = 5
    max_inflight_jobs: int = 12
    max_failed_jobs: int = 5

    def __post_init__(self) -> None:
        values = (
            self.max_actions,
            self.max_scans,
            self.max_validations,
            self.max_validation_batch,
            self.max_reports,
            self.max_inflight_jobs,
            self.max_failed_jobs,
        )
        if any(value < 1 for value in values):
            raise ValueError("planner budget limits must be positive")
        if self.max_validation_batch > self.max_validations:
            raise ValueError("max_validation_batch cannot exceed max_validations")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BudgetUsage:
    actions: int
    scans: int
    validations: int
    reports: int
    inflight_jobs: int
    failed_jobs: int
    remaining_actions: int
    remaining_scans: int
    remaining_validations: int
    remaining_reports: int
    remaining_inflight_jobs: int
    remaining_failed_jobs: int
    blocked_actions: dict[str, str]
    exhausted: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blocked_actions(
    *,
    actions: int,
    scans: int,
    validations: int,
    reports: int,
    inflight_jobs: int,
    failed_jobs: int,
    limits: PlannerBudget,
) -> dict[str, str]:
    if actions >= limits.max_actions:
        return {
            kind: "planner action budget exhausted"
            for kind in ("inventory", "crawl", "scan", "validate", "report")
        }

    blocked: dict[str, str] = {}
    if failed_jobs >= limits.max_failed_jobs:
        for kind in ("scan", "validate", "report"):
            blocked[kind] = "failed job budget exhausted"
    if inflight_jobs >= limits.max_inflight_jobs:
        for kind in ("scan", "validate", "report"):
            blocked[kind] = "in-flight job budget exhausted"
    if scans >= limits.max_scans:
        blocked["scan"] = "scan budget exhausted"
    if validations >= limits.max_validations:
        blocked["validate"] = "validation budget exhausted"
    if reports >= limits.max_reports:
        blocked["report"] = "report budget exhausted"
    return blocked


def budget_usage(
    graph: ObservationGraph,
    queue: JobQueue,
    campaign_id: str,
    budget: PlannerBudget | None = None,
) -> BudgetUsage:
    limits = budget or PlannerBudget()
    history = decision_history(graph)
    counts = queue.campaign_job_counts(campaign_id)
    status_counts = queue.campaign_job_status_counts(campaign_id)
    actions = sum(1 for item in history if item.get("action") != "stop")
    scans = counts["strix_scan"]
    validations = counts["independent_validation"]
    reports = counts["report"]
    inflight_jobs = status_counts["queued"] + status_counts["running"]
    failed_jobs = status_counts["failed"]
    blocked_actions = _blocked_actions(
        actions=actions,
        scans=scans,
        validations=validations,
        reports=reports,
        inflight_jobs=inflight_jobs,
        failed_jobs=failed_jobs,
        limits=limits,
    )
    exhausted = actions >= limits.max_actions

    return BudgetUsage(
        actions=actions,
        scans=scans,
        validations=validations,
        reports=reports,
        inflight_jobs=inflight_jobs,
        failed_jobs=failed_jobs,
        remaining_actions=max(0, limits.max_actions - actions),
        remaining_scans=max(0, limits.max_scans - scans),
        remaining_validations=max(0, limits.max_validations - validations),
        remaining_reports=max(0, limits.max_reports - reports),
        remaining_inflight_jobs=max(0, limits.max_inflight_jobs - inflight_jobs),
        remaining_failed_jobs=max(0, limits.max_failed_jobs - failed_jobs),
        blocked_actions=blocked_actions,
        exhausted=exhausted,
        reason="planner action budget exhausted" if exhausted else None,
    )


def apply_budget(
    action: PlannedAction,
    graph: ObservationGraph,
    queue: JobQueue,
    campaign_id: str,
    budget: PlannerBudget | None = None,
) -> tuple[PlannedAction, BudgetUsage]:
    limits = budget or PlannerBudget()
    usage = budget_usage(graph, queue, campaign_id, limits)
    reason = usage.blocked_actions.get(action.kind)

    if reason is None:
        return action, usage

    return (
        PlannedAction(
            kind="stop",
            target=action.target,
            reason=reason,
            priority=100,
        ),
        BudgetUsage(
            **{
                **usage.to_dict(),
                "exhausted": True,
                "reason": reason,
            }
        ),
    )


def validation_batch_limit(usage: BudgetUsage, budget: PlannerBudget | None = None) -> int:
    limits = budget or PlannerBudget()
    return max(
        0,
        min(
            limits.max_validation_batch,
            usage.remaining_validations,
            usage.remaining_inflight_jobs,
        ),
    )
