from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .campaign_risk import CampaignRisk, build_campaign_risk
from .campaign_runtime import CampaignRuntimeLimit, runtime_status
from .decision_consensus import DecisionConsensus, build_decision_consensus
from .observation_graph import load_observation_graph
from .planner_budget import PlannerBudget, budget_usage
from .red_team_decision import build_red_team_decisions

router = APIRouter()


@dataclass(frozen=True)
class AutonomyGate:
    safe_autonomy_ready: bool
    human_review_required: bool
    next_focus: str
    blockers: tuple[str, ...]
    safeguards: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["safeguards"] = list(self.safeguards)
        return payload


def build_autonomy_gate(
    *,
    automated_scanning: bool,
    destructive_testing: bool,
    denial_of_service: bool,
    social_engineering: bool,
    credential_attacks: bool,
    runtime_exhausted: bool,
    budget_blocked: bool,
    failed_jobs: int,
    risk: CampaignRisk,
    consensus: DecisionConsensus,
) -> AutonomyGate:
    """Fail closed before any autonomous safe-review progression.

    The gate is read-only: it never queues jobs, changes finding state, or performs
    network actions. It only decides whether the current campaign state is safe
    enough for already-authorized bounded automation to continue elsewhere.
    """
    blockers: list[str] = []

    if not automated_scanning:
        blockers.append("automated_scanning_disabled")
    if destructive_testing:
        blockers.append("destructive_testing_enabled")
    if denial_of_service:
        blockers.append("denial_of_service_enabled")
    if social_engineering:
        blockers.append("social_engineering_enabled")
    if credential_attacks:
        blockers.append("credential_attacks_enabled")
    if runtime_exhausted:
        blockers.append("runtime_exhausted")
    if budget_blocked:
        blockers.append("budget_blocked")
    if failed_jobs:
        blockers.append("failed_jobs")
    if risk.blocked:
        blockers.append("campaign_risk_blocked")
    if consensus.blocked:
        blockers.append("decision_consensus_blocked")

    blockers = sorted(set(blockers))
    human_review_required = consensus.next_focus == "review_for_report" or risk.level in {
        "high",
        "critical",
    }

    safeguards = (
        "explicit_scope_required",
        "bounded_runtime",
        "bounded_budget",
        "non_destructive_only",
        "human_report_review",
        "fail_closed_on_conflict",
    )

    return AutonomyGate(
        safe_autonomy_ready=not blockers and not human_review_required,
        human_review_required=human_review_required,
        next_focus=consensus.next_focus,
        blockers=tuple(blockers),
        safeguards=safeguards,
    )


@router.get("/api/campaigns/{campaign_id}/autonomy-gate")
def campaign_autonomy_gate(campaign_id: str):
    from .main import assert_campaign_exists, is_host_allowed, queue, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    decisions = build_red_team_decisions(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
        limit=10,
    )
    consensus = build_decision_consensus(decisions)
    risk = build_campaign_risk(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
    )
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
    return {
        "campaign_id": campaign.id,
        "gate": gate.to_dict(),
        "read_only": True,
        "fail_closed": True,
    }
