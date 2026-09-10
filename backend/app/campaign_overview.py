from __future__ import annotations

from collections import Counter

from fastapi import APIRouter

from .knowledge_memory import build_knowledge_snapshot
from .observation_graph import load_observation_graph
from .planner_budget import PlannerBudget, budget_usage
from .storage import ArtifactIntegrityError
from .submission_state import submission_status
from .validation_state import analyze_validation_state

router = APIRouter()


@router.get("/api/campaigns/{campaign_id}/overview")
def campaign_overview(campaign_id: str):
    from .main import assert_campaign_record, queue, storage

    campaign, version = assert_campaign_record(campaign_id)
    store = storage()
    jobs = queue()
    graph = load_observation_graph(store, campaign.id)
    validation = analyze_validation_state(graph)
    knowledge = build_knowledge_snapshot(graph)
    limits = PlannerBudget()
    budget = budget_usage(graph, jobs, campaign.id, limits)

    finding_counts = Counter(str(item.status) for item in campaign.findings)
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

    return {
        "campaign_id": campaign.id,
        "version": version,
        "state": campaign.state.value,
        "updated_at": campaign.updated_at,
        "findings": {
            "total": len(campaign.findings),
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
        "observations": knowledge.to_dict(),
        "jobs": {
            "by_kind": job_kinds,
            "by_status": job_statuses,
            "inflight": job_statuses["queued"] + job_statuses["running"],
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
            "by_state": {
                state: report_states.get(state, 0)
                for state in ("draft", "review_required", "approved", "submitted")
            },
        },
        "attention_required": bool(
            report_integrity_errors
            or blocked
            or validation.unresolved_finding_ids
            or job_statuses["failed"]
        ),
    }
