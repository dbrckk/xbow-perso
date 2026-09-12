from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .agent_registry import agent_for_action
from .planner_budget import BudgetUsage, PlannerBudget


@dataclass(frozen=True)
class PipelineCoordination:
    action: str
    agent: str
    role: str
    requested_items: int
    allocated_items: int
    remaining_inflight_jobs: int
    bounded: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def coordinate_pipeline_action(
    action: str,
    requested_items: int,
    usage: BudgetUsage,
    budget: PlannerBudget | None = None,
) -> PipelineCoordination:
    if action not in {"scan", "validate", "report"}:
        raise ValueError(f"unsupported pipeline action: {action}")
    if requested_items < 0:
        raise ValueError("requested_items must be non-negative")

    limits = budget or PlannerBudget()
    agent = agent_for_action(action)
    expected_roles = {
        "scan": "analysis",
        "validate": "validation",
        "report": "reporting",
    }
    if agent.role != expected_roles[action]:
        raise ValueError(f"pipeline agent role mismatch for {action}")

    if action == "scan":
        action_capacity = usage.remaining_scans
        batch_capacity = limits.max_scans
    elif action == "validate":
        action_capacity = usage.remaining_validations
        batch_capacity = limits.max_validation_batch
    else:
        action_capacity = usage.remaining_reports
        batch_capacity = 1

    allocated = max(
        0,
        min(
            requested_items,
            action_capacity,
            usage.remaining_inflight_jobs,
            batch_capacity,
        ),
    )
    return PipelineCoordination(
        action=action,
        agent=agent.name,
        role=agent.role,
        requested_items=requested_items,
        allocated_items=allocated,
        remaining_inflight_jobs=max(0, usage.remaining_inflight_jobs - allocated),
    )
