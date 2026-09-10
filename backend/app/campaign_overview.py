from __future__ import annotations

from collections import Counter

from fastapi import APIRouter

from .attack_surface import build_attack_surface, router as attack_surface_router
from .campaign_runtime import CampaignRuntimeLimit, runtime_status
from .knowledge_memory import build_knowledge_snapshot
from .observation_graph import load_observation_graph
from .planner_budget import PlannerBudget, budget_usage
from .storage import ArtifactIntegrityError
from .submission_state import submission_status
from .validation_state import analyze_validation_state

router = APIRouter()
router.routes.extend(attack_surface_router.routes)


@router.get("/api/campaigns/{campaign_id}/overview")
def campaign_overview(campaign_id: str):
    from .main import assert_campaign_record, queue, storage

    campaign, version = assert_campaign_record(campaign_id)
    store = storage()
    jobs = queue()
    graph = load_observation_graph(store, campaign.id)
    validation = analyze_validation_state(graph)
    knowledge = build_knowledge_snapshot(graph)
    surface = build_attack_surface(graph)
    limits = PlannerBudget()
    budget = budget_usage(graph, jobs, campaign.id, limits)
    runtime_limit = CampaignRuntimeLimit()
    runtime = runtime_status(campaign.created_at, runtime_limit)

    finding_counts = Counter(str(item.status) for item in campaign.findings)
    resolved_findings = finding_counts.get("confirmed", 0) + finding_counts.get("rejected", 0)
    report_states = Counter()
    report_integrity_errors = 0
    reports = []
    for artifact in store.list_artifacts(campaign.id):
        if artifact.get("kind") != "report":
            continue
        try:
            verified, _content = store.read_artifact(campaign.id, artifact["id"])
        except ArtifactIntegrityError:
            report_integrity_errors += 1
            continue
        status = submission_status(campaign, verified).to_dict()
        reports.append(status)
        report_states[status["state"]] += 1

    job_kinds = jobs.campaign_job_counts(campaign.id)
    job_statuses = jobs.campaign_job_status_counts(campaign.id)
    blocked = dict(budget.blocked_actions)
    terminal_campaign = campaign.state.value in {"completed", "failed", "cancelled"}
    attention_reasons = []
    if report_integrity_errors:
        attention_reasons.append("report_integrity_error")
    if blocked:
        attention_reasons.append("budget_blocked")
    if runtime.exhausted and not terminal_campaign:
        attention_reasons.append("runtime_exhausted")
    if surface["summary"]["invalid_endpoint_count"]:
        attention_reasons.append("invalid_attack_surface_endpoint")
    if validation.unresolved_finding_ids:
        attention_reasons.append("unresolved_validation")
    if job_statuses["failed"]:
        attention_reasons.append("failed_jobs")

    latest_event = campaign.events[-1] if campaign.events else None
    rules = campaign.target.rules
    total_findings = len(campaign.findings)

    return {
        "campaign_id": campaign.id,
        "version": version,
        "state": campaign.state.value,
        "updated_at": campaign.updated_at,
        "target": {
            "name": campaign.target.name,
            "primary_url": str(campaign.target.primary_url),
        },
        "policy": {
            "authorization_reference": rules.authorization_reference,
            "automated_scanning": rules.automated_scanning,
            "max_requests_per_second": rules.max_requests_per_second,
            "allowed_target_count": len(rules.allowed_targets),
            "denied_target_count": len(rules.denied_targets),
            "destructive_testing": rules.destructive_testing,
            "denial_of_service": rules.denial_of_service,
            "social_engineering": rules.social_engineering,
            "credential_attacks": rules.credential_attacks,
        },
        "runtime": {
            "limit": runtime_limit.to_dict(),
            "status": runtime.to_dict(),
            "terminal_campaign": terminal_campaign,
        },
        "findings": {
            "total": total_findings,
            "resolved": resolved_findings,
            "unresolved": max(0, total_findings - resolved_findings),
            "resolution_ratio": round(resolved_findings / total_findings, 4) if total_findings else 1.0,
            "by_status": {
                state: finding_counts.get(state, 0)
                for state in ("candidate", "validation_required", "confirmed", "rejected")
            },
        },
        "validation": {
            "graph_findings": len(validation.finding_ids),
            "attempted": len(validation.attempted_finding_ids),
            "observed_independent": len(validation.observed_independent_finding_ids),
            "unresolved": len(validation.unresolved_finding_ids),
            "unattempted": len(validation.unattempted_finding_ids),
            "all_observed_independently": validation.all_observed_independently,
        },
        "attack_surface": {
            "summary": surface["summary"],
            "read_only": surface["read_only"],
        },
        "observations": knowledge.to_dict(),
        "jobs": {
            "by_kind": job_kinds,
            "by_status": job_statuses,
            "inflight": job_statuses["queued"] + job_statuses["running"],
            "terminal": job_statuses["completed"] + job_statuses["failed"] + job_statuses["cancelled"],
        },
        "budget": {
            "limits": limits.to_dict(),
            "usage": budget.to_dict(),
            "blocked": bool(blocked),
            "blocked_actions": blocked,
        },
        "reports": {
            "total": len(reports) + report_integrity_errors,
            "verified": len(reports),
            "integrity_errors": report_integrity_errors,
            "submission_ready": report_states.get("approved", 0),
            "submitted": report_states.get("submitted", 0),
            "by_state": {
                state: report_states.get(state, 0)
                for state in ("draft", "review_required", "approved", "submitted")
            },
        },
        "activity": {
            "event_count": len(campaign.events),
            "latest_event_type": latest_event.get("type") if latest_event else None,
            "latest_event_at": latest_event.get("at") if latest_event else None,
        },
        "attention_required": bool(attention_reasons),
        "attention_reasons": attention_reasons,
    }
