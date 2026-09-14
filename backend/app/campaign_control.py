from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .campaign_runtime import campaign_runtime_limit_from_env, runtime_status
from .circuit_breaker import circuit_breaker_state, record_circuit_reset
from .decision_timeline import planner_stability_from_graph
from .observation_graph import load_observation_graph
from .planner_budget import budget_usage, planner_budget_from_env
from .planner_limits import planner_limits
from .runtime_capabilities import safe_scanner_runtime_capability

router = APIRouter()


def _recon_telemetry(events: list[dict]) -> dict:
    completed = [event for event in events if event.get("type") == "recon_task_completed"]
    return {
        "completed_tasks": len(completed),
        "requests_made": sum(int(event.get("requests_made") or 0) for event in completed),
        "bytes_read": sum(int(event.get("bytes_read") or 0) for event in completed),
        "max_depth_reached": max(
            (int(event.get("max_depth_reached") or 0) for event in completed),
            default=0,
        ),
        "skipped_out_of_scope": sum(
            int(event.get("skipped_out_of_scope") or 0) for event in completed
        ),
        "skipped_cross_origin": sum(
            int(event.get("skipped_cross_origin") or 0) for event in completed
        ),
        "wall_time_seconds": round(
            sum(float(event.get("wall_time_seconds") or 0.0) for event in completed),
            3,
        ),
        "time_budget_stops": sum(
            1 for event in completed if bool(event.get("stopped_by_time_budget"))
        ),
        "request_budget_stops": sum(
            1 for event in completed if bool(event.get("stopped_by_request_budget"))
        ),
        "incomplete_tasks": sum(
            1 for event in completed if not bool(event.get("coverage_complete"))
        ),
        "frontier_remaining": sum(
            int(event.get("frontier_remaining") or 0) for event in completed
        ),
        "deferred_by_request_budget": sum(
            int(event.get("deferred_by_request_budget") or 0) for event in completed
        ),
    }


def _autonomy_block_reasons(breaker: dict, runtime: object, usage: object) -> list[str]:
    reasons: list[str] = []
    if breaker.get("open"):
        reasons.append("circuit_breaker_open")
    if bool(getattr(runtime, "exhausted", False)):
        reasons.append("runtime_exhausted")
    if bool(getattr(usage, "blocked_actions", {})):
        reasons.append("budget_blocked")
    return reasons


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
    stability = planner_stability_from_graph(graph)
    scanner = safe_scanner_runtime_capability()
    recon = _recon_telemetry(campaign.events)
    block_reasons = _autonomy_block_reasons(breaker, runtime, usage)

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
        "planner_stability": stability,
        "scanner_execution": scanner,
        "recon_telemetry": recon,
        "autonomy_blocked": bool(block_reasons),
        "autonomy_block_reasons": block_reasons,
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
