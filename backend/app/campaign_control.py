from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException

from .campaign_audit import append_campaign_event
from .campaign_runtime import campaign_runtime_limit_from_env, runtime_status
from .circuit_breaker import circuit_breaker_state, record_circuit_reset
from .decision_timeline import planner_stability_from_graph
from .hackerone_api import router as hackerone_router
from .observation_graph import load_observation_graph
from .planner_budget import budget_usage, planner_budget_from_env
from .planner_limits import planner_limits
from .runtime_capabilities import safe_scanner_runtime_capability

router = APIRouter()
router.routes.extend(hackerone_router.routes)


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


def _breaker_reset_request_id(breaker: dict) -> str:
    opened_at = str(breaker.get("opened_at") or "")
    reason = str(breaker.get("reason") or "")
    digest = hashlib.sha256(
        f"{opened_at}\x1f{reason}".encode("utf-8")
    ).hexdigest()[:24]
    return f"breaker-reset:{digest}"


def _event_exists(events: list[dict], event_type: str, request_id: str) -> bool:
    return any(
        event.get("type") == event_type
        and event.get("request_id") == request_id
        for event in events
    )


def _pending_breaker_reset(events: list[dict]) -> str | None:
    completed = {
        str(event.get("request_id"))
        for event in events
        if event.get("type") == "circuit_breaker_reset_completed"
        and event.get("request_id")
    }
    for event in reversed(events):
        if (
            event.get("type") == "circuit_breaker_reset_requested"
            and event.get("request_id")
            and str(event["request_id"]) not in completed
        ):
            return str(event["request_id"])
    return None


def _persist_breaker_reset_event(
    campaign_id: str,
    event_type: str,
    request_id: str,
    **fields,
):
    from .main import assert_campaign_record, save_campaign, utcnow

    for _ in range(3):
        campaign, version = assert_campaign_record(campaign_id)
        if _event_exists(campaign.events, event_type, request_id):
            return campaign
        append_campaign_event(
            campaign.events,
            {
                "type": event_type,
                "request_id": request_id,
                "at": utcnow(),
                **fields,
            },
        )
        campaign.updated_at = utcnow()
        try:
            save_campaign(campaign, expected_version=version)
            return campaign
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
    raise HTTPException(
        status_code=409,
        detail="Circuit breaker reset audit reconciliation conflicted; retry safely",
    )


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

    store = storage()
    graph = load_observation_graph(store, campaign.id)
    breaker = circuit_breaker_state(graph)
    pending_request_id = _pending_breaker_reset(campaign.events)

    if not breaker["open"] and pending_request_id is None:
        return {
            "campaign_id": campaign.id,
            "circuit_breaker": breaker,
            "operator_action": False,
            "audit_reconciled": True,
        }

    request_id = pending_request_id or _breaker_reset_request_id(breaker)
    if breaker["open"]:
        _persist_breaker_reset_event(
            campaign.id,
            "circuit_breaker_reset_requested",
            request_id,
            breaker_opened_at=breaker.get("opened_at"),
            breaker_reason=breaker.get("reason"),
        )
        state = record_circuit_reset(store, campaign.id, at=utcnow())
    else:
        state = breaker

    _persist_breaker_reset_event(
        campaign.id,
        "circuit_breaker_reset_completed",
        request_id,
        reset_at=state.get("reset_at"),
    )
    return {
        "campaign_id": campaign.id,
        "circuit_breaker": state,
        "operator_action": True,
        "request_id": request_id,
        "audit_reconciled": True,
    }
