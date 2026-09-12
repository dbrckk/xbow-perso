from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from fastapi import APIRouter

from .autonomy_gate import AutonomyGate, build_autonomy_gate
from .campaign_risk import build_campaign_risk
from .campaign_runtime import CampaignRuntimeLimit, runtime_status
from .decision_consensus import build_decision_consensus
from .learning_memory import TechniqueMemory, build_learning_memory, summarize_worker_outcomes
from .observation_graph import AdaptivePlanner, PlannedAction, load_observation_graph
from .planner_budget import PlannerBudget, budget_usage
from .red_team_decision import build_red_team_decisions

CycleState = Literal["halt", "recon", "review", "validate", "human_review", "complete"]

router = APIRouter()


@dataclass(frozen=True)
class AdaptiveCycle:
    state: CycleState
    next_action: str
    reason: str
    retry_suppressed_techniques: tuple[str, ...]
    retry_suppressed_job_kinds: tuple[str, ...]
    safe_to_progress: bool
    requires_human: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["retry_suppressed_techniques"] = list(self.retry_suppressed_techniques)
        payload["retry_suppressed_job_kinds"] = list(self.retry_suppressed_job_kinds)
        return payload


def _suppressed_techniques(memories: list[TechniqueMemory]) -> tuple[str, ...]:
    return tuple(
        sorted(
            item.technique
            for item in memories
            if item.failures >= 2 and item.successes == 0 and item.confidence >= 0.2
        )
    )


def _unstable_job_kinds(worker_outcomes: dict[str, Any] | None) -> tuple[str, ...]:
    if not worker_outcomes:
        return ()
    by_kind = worker_outcomes.get("by_job_kind")
    if not isinstance(by_kind, dict):
        return ()
    unstable = []
    for kind, values in by_kind.items():
        if not isinstance(values, dict):
            continue
        requeued = int(values.get("requeued") or 0)
        completed = int(values.get("completed") or 0)
        if requeued >= 2 and completed == 0:
            unstable.append(str(kind))
    return tuple(sorted(set(unstable)))


def build_adaptive_cycle(
    gate: AutonomyGate,
    planned_actions: list[PlannedAction],
    memories: list[TechniqueMemory],
    worker_outcomes: dict[str, Any] | None = None,
) -> AdaptiveCycle:
    """Resolve one bounded campaign cycle without executing target actions."""
    suppressed = _suppressed_techniques(memories)
    unstable_jobs = _unstable_job_kinds(worker_outcomes)

    if gate.blockers:
        return AdaptiveCycle(
            state="halt",
            next_action="stop",
            reason="autonomy gate is blocked",
            retry_suppressed_techniques=suppressed,
            retry_suppressed_job_kinds=unstable_jobs,
            safe_to_progress=False,
            requires_human=gate.human_review_required,
        )
    if unstable_jobs:
        return AdaptiveCycle(
            state="human_review",
            next_action="stop",
            reason="worker outcome feedback indicates unstable execution",
            retry_suppressed_techniques=suppressed,
            retry_suppressed_job_kinds=unstable_jobs,
            safe_to_progress=False,
            requires_human=True,
        )
    if gate.human_review_required:
        return AdaptiveCycle(
            state="human_review",
            next_action=gate.next_focus,
            reason="campaign requires explicit human review",
            retry_suppressed_techniques=suppressed,
            retry_suppressed_job_kinds=unstable_jobs,
            safe_to_progress=False,
            requires_human=True,
        )

    action = planned_actions[0] if planned_actions else PlannedAction("stop", None, "no planner action", 100)
    if action.kind == "stop":
        terminal = "already exists" in action.reason or "all findings rejected" in action.reason
        return AdaptiveCycle(
            state="complete" if terminal else "halt",
            next_action="stop",
            reason=action.reason,
            retry_suppressed_techniques=suppressed,
            retry_suppressed_job_kinds=unstable_jobs,
            safe_to_progress=False,
            requires_human=False,
        )

    state_by_action: dict[str, CycleState] = {
        "inventory": "recon",
        "crawl": "recon",
        "scan": "review",
        "validate": "validate",
        "report": "human_review",
    }
    state = state_by_action.get(action.kind, "halt")
    requires_human = action.kind == "report"
    return AdaptiveCycle(
        state=state,
        next_action=action.kind,
        reason=action.reason,
        retry_suppressed_techniques=suppressed,
        retry_suppressed_job_kinds=unstable_jobs,
        safe_to_progress=not requires_human,
        requires_human=requires_human,
    )


@router.get("/api/campaigns/{campaign_id}/adaptive-cycle")
def campaign_adaptive_cycle(campaign_id: str):
    from .main import assert_campaign_exists, is_host_allowed, queue, storage

    campaign = assert_campaign_exists(campaign_id)
    store = storage()
    graph = load_observation_graph(store, campaign.id)
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    decisions = build_red_team_decisions(campaign.findings, graph, scope_checker=scope_checker, limit=10)
    consensus = build_decision_consensus(decisions)
    risk = build_campaign_risk(campaign.findings, graph, scope_checker=scope_checker)
    limits = PlannerBudget()
    budget = budget_usage(graph, queue(), campaign.id, limits)
    runtime = runtime_status(campaign.created_at, CampaignRuntimeLimit())
    job_statuses = queue().campaign_job_status_counts(campaign.id)
    gate = build_autonomy_gate(
        automated_scanning=rules.automated_scanning,
        destructive_testing=rules.destructive_testing,
        denial_of_service=rules.denial_of_service,
        social_engineering=rules.social_engineering,
        credential_attacks=rules.credential_attacks,
        runtime_exhausted=runtime.exhausted,
        budget_blocked=bool(budget.blocked_actions),
        failed_jobs=job_statuses["failed"],
        risk=risk,
        consensus=consensus,
    )
    planned = AdaptivePlanner().plan(campaign, graph)
    memories = build_learning_memory(graph)
    worker_outcomes = summarize_worker_outcomes(campaign.events)
    cycle = build_adaptive_cycle(gate, planned, memories, worker_outcomes)
    return {
        "campaign_id": campaign.id,
        "cycle": cycle.to_dict(),
        "read_only": True,
        "bounded": True,
        "fail_closed": True,
    }
