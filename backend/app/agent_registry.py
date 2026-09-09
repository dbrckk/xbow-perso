from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

AgentRole = Literal["recon", "analysis", "validation", "reporting", "control"]


@dataclass(frozen=True)
class AgentProfile:
    name: str
    role: AgentRole
    actions: tuple[str, ...]
    description: str
    network_access: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


AGENTS: tuple[AgentProfile, ...] = (
    AgentProfile(
        name="scope-coordinator",
        role="control",
        actions=("inventory", "stop"),
        description="Enforces authorization, scope and campaign stop conditions.",
    ),
    AgentProfile(
        name="recon-agent",
        role="recon",
        actions=("crawl",),
        description="Builds the authorized asset and endpoint inventory.",
        network_access=True,
    ),
    AgentProfile(
        name="analysis-agent",
        role="analysis",
        actions=("scan",),
        description="Runs bounded, policy-checked analysis through approved scanners.",
        network_access=True,
    ),
    AgentProfile(
        name="validation-agent",
        role="validation",
        actions=("validate",),
        description="Collects independent, non-destructive validation evidence.",
        network_access=True,
    ),
    AgentProfile(
        name="report-agent",
        role="reporting",
        actions=("report",),
        description="Correlates validated evidence and generates submission-ready reports.",
    ),
)


def agent_for_action(action: str) -> AgentProfile:
    matches = [agent for agent in AGENTS if action in agent.actions]
    if len(matches) != 1:
        raise ValueError(f"no unique agent registered for action: {action}")
    return matches[0]


def public_agent_catalog() -> list[dict]:
    return [agent.to_dict() for agent in AGENTS]
