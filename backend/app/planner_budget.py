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

    def __post_init__(self) -> None:
        values = (
            self.max_actions,
            self.max_scans,
            self.max_validations,
            self.max_validation_batch,
            self.max_reports,
            self.max_inflight_jobs,
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
    remaining_actions: int
    remaining_scans: int
    remaining_validations: int
    remaining_reports: int
    remaining_inflight_jobs: int
    exhausted: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    exhausted = actions >= limits.max_actions

    return BudgetUsage(
        actions=actions,
        scans=scans,
        validations=validations,
        reports=reports,
        inflight_jobs=inflight_jobs,
        remaining_actions=max(0, limits.max_actions - actions),
        remaining_scans=max(0, limits.max_scans - scans),
        remaining_validations=max(0, limits.max_validations - validations),
        remaining_reports=max(0, limits.max_reports - reports),
        remaining_inflight_jobs=max(0, limits.max_inflight_jobs - inflight_jobs),
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

    reason = None
    if usage.actions >= limits.max_actions:
        reason = "planner action budget exhausted"
    elif action.kind in {"scan", "validate", "report"} and usage.inflight_jobs >= limits.max_inflight_jobs:
        reason = "in-flight job budget exhausted"
    elif action.kind == "scan" and usage.scans >= limits.max_scans:
        reason = "scan budget exhausted"
    elif action.kind == "validate" and usage.validations >= limits.max_validations:
        reason = "validation budget exhausted"
    elif action.kind == "report" and usage.reports >= limits.max_reports:
        reason = "report budget exhausted"

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
