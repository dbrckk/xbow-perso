from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .campaign_runtime import campaign_runtime_limit_from_env, runtime_status
from .circuit_breaker import circuit_breaker_state, record_circuit_reset
from .observation_graph import load_observation_graph
from .planner_budget import budget_usage, planner_budget_from_env
from .planner_limits import planner_limits

router = APIRouter()


@router.get("/api/campaigns/{campaign_id}/control-status")
def campaign_control_status(campaign_id: str):
    from .main import assert_campaign_exists, queue, storage

    campaign = assert_campaign_exists(campaign_id)
    store = storage()
    jobs = queue()
    graph = load_observation_graph(store, campaign.id)
    budget_limits = planner_budget_from_env()
    runtime_limit = campaign_runtime_limit_from_env()
    usage = budget_usage(graph, jobs, campaign.id, budget_limits)
    runtime = runtime_status(campaign.created_at, runtime_limit)
    statuses = jobs.campaign_job_status_counts(campaign.id)
    breaker = circuit_breaker_state(graph)

    return {
        "campaign_id": campaign.id,
        "campaign_state": campaign.state,
        "circuit_breaker": breaker,
        "runtime": {
            "limit_seconds": runtime_limit.max_runtime_seconds,
            **runtime.to_dict(),
        },
        "budget": {
            "limits": budget_limits.to_dict(),
            "usage": usage.to_dict(),
        },
        "graph_limits": planner_limits().__dict__,
        "jobs": statuses,
        "autonomy_blocked": bool(
            breaker["open"] or runtime.exhausted or usage.exhausted
        ),
        "read_only": True,
        "fail_closed": True,
    }


@router.post("/api/campaigns/{campaign_id}/circuit-breaker/reset")
def reset_campaign_circuit_breaker(campaign_id: str):
    from .main import CampaignState, assert_campaign_exists, storage, utcnow

    campaign = assert_campaign_exists(campaign_id)
    if campaign.state in {CampaignState.cancelled, CampaignState.completed}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reset circuit breaker for {campaign.state.value} campaign",
        )
    state = record_circuit_reset(storage(), campaign.id, at=utcnow())
    return {
        "campaign_id": campaign.id,
        "circuit_breaker": state,
        "operator_action": True,
    }
