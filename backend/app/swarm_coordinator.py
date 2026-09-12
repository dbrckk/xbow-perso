from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from .agent_registry import agent_by_name
from .recon_swarm import ReconCapability, ReconTask, recon_capabilities


@dataclass(frozen=True)
class SwarmBudget:
    max_tasks: int = 5
    max_total_requests: int = 80
    max_network_agents: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.max_tasks <= 10:
            raise ValueError("max_tasks must be between 1 and 10")
        if not 1 <= self.max_total_requests <= 200:
            raise ValueError("max_total_requests must be between 1 and 200")
        if not 1 <= self.max_network_agents <= 10:
            raise ValueError("max_network_agents must be between 1 and 10")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SwarmCoordination:
    tasks: tuple[ReconTask, ...]
    request_budget_used: int
    request_budget_remaining: int
    active_agents: tuple[str, ...]
    suppressed_tasks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [item.to_dict() for item in self.tasks],
            "request_budget_used": self.request_budget_used,
            "request_budget_remaining": self.request_budget_remaining,
            "active_agents": list(self.active_agents),
            "suppressed_tasks": list(self.suppressed_tasks),
            "read_only": True,
            "bounded": True,
        }


def _capability_by_task() -> dict[str, ReconCapability]:
    capabilities = recon_capabilities()
    mapping = {item.task_kind: item for item in capabilities}
    if len(mapping) != len(capabilities):
        raise ValueError("recon capabilities must map uniquely by task kind")
    return mapping


def coordinate_recon_swarm(
    tasks: list[ReconTask],
    budget: SwarmBudget | None = None,
) -> SwarmCoordination:
    limits = budget or SwarmBudget()
    capabilities = _capability_by_task()
    selected: list[ReconTask] = []
    suppressed: list[str] = []
    agents: set[str] = set()
    used = 0

    for task in sorted(tasks, key=lambda item: (-item.priority, item.kind, item.agent)):
        capability = capabilities.get(task.kind)
        if capability is None:
            raise ValueError(f"no registered capability for recon task: {task.kind}")
        if task.agent != capability.agent:
            raise ValueError(f"recon task agent mismatch for {task.kind}")
        profile = agent_by_name(task.agent)
        if profile.role != "recon":
            raise ValueError("recon task agent must have recon role")
        if profile.network_access != capability.network_access:
            raise ValueError("recon agent network capability mismatch")
        expected_action = f"recon:{task.kind}"
        if expected_action not in profile.actions:
            raise ValueError("recon agent action registration mismatch")
        if not task.read_only or not task.same_origin_only:
            raise ValueError("recon swarm only accepts read-only same-origin tasks")
        if not set(task.allowed_methods) <= set(capability.allowed_methods):
            raise ValueError("recon task methods exceed agent capability")
        if task.max_requests < 1 or task.max_requests > capability.max_requests_per_target:
            raise ValueError("recon task request budget exceeds agent capability")

        if len(selected) >= limits.max_tasks:
            suppressed.append(task.kind)
            continue
        if capability.network_access and task.agent not in agents and len(agents) >= limits.max_network_agents:
            suppressed.append(task.kind)
            continue

        remaining = limits.max_total_requests - used
        if remaining <= 0:
            suppressed.append(task.kind)
            continue

        allocated = min(task.max_requests, remaining)
        if allocated < 1:
            suppressed.append(task.kind)
            continue

        selected.append(replace(task, max_requests=allocated))
        used += allocated
        if capability.network_access:
            agents.add(task.agent)

    return SwarmCoordination(
        tasks=tuple(selected),
        request_budget_used=used,
        request_budget_remaining=max(0, limits.max_total_requests - used),
        active_agents=tuple(sorted(agents)),
        suppressed_tasks=tuple(suppressed),
    )
