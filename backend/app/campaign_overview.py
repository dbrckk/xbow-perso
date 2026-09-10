from __future__ import annotations

from collections import Counter

from fastapi import APIRouter

from .attack_surface import build_attack_surface, router as attack_surface_router
from .campaign_risk import build_campaign_risk, router as campaign_risk_router
from .campaign_runtime import CampaignRuntimeLimit, runtime_status
from .decision_consensus import build_decision_consensus, router as decision_consensus_router
from .evidence_chain import build_evidence_chains
from .finding_correlation import correlate_findings
from .finding_triage import build_finding_triage, router as finding_triage_router
from .hypothesis_engine import build_hypotheses
from .knowledge_memory import build_knowledge_snapshot
from .observation_graph import load_observation_graph
from .planner_budget import PlannerBudget, budget_usage
from .red_team_coverage import build_red_team_coverage, router as red_team_coverage_router
from .red_team_decision import build_red_team_decisions, router as red_team_decision_router
from .review_queue import build_review_queue, router as review_queue_router
from .storage import ArtifactIntegrityError
from .submission_state import submission_status
from .validation_state import analyze_validation_state

router = APIRouter()
router.routes.extend(attack_surface_router.routes)
router.routes.extend(red_team_coverage_router.routes)
router.routes.extend(review_queue_router.routes)
router.routes.extend(finding_triage_router.routes)
router.routes.extend(red_team_decision_router.routes)
router.routes.extend(decision_consensus_router.routes)
router.routes.extend(campaign_risk_router.routes)


@router.get("/api/campaigns/{campaign_id}/overview")
def campaign_overview(campaign_id: str):
    from .main import assert_campaign_record, is_host_allowed, queue, storage

    campaign, version = assert_campaign_record(campaign_id)
    store = storage()
    jobs = queue()
    graph = load_observation_graph(store, campaign.id)
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    validation = analyze_validation_state(graph)
    knowledge = build_knowledge_snapshot(graph)
    surface = build_attack_surface(graph, scope_checker=scope_checker)
    hypotheses = build_hypotheses(graph, scope_checker=scope_checker)
    chains = build_evidence_chains(graph)
    correlations = correlate_findings(campaign.findings)
    triage = build_finding_triage(campaign.findings, graph)
    coverage = build_red_team_coverage(graph, scope_checker=scope_checker)
    review_tasks = build_review_queue(graph, scope_checker=scope_checker)
    decisions = build_red_team_decisions(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
    )
    consensus = build_decision_consensus(decisions)
    risk = build_campaign_risk(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
    )
    limits = PlannerBudget()
    budget = budget_usage(graph, jobs, campaign.id, limits)
    runtime_limit = CampaignRuntimeLimit()
    runtime = runtime_status(campaign.created_at, runtime_limit)

    finding_counts = Counter(str(item.status) for item in campaign.findings)
    resolved_findings = finding_counts.get("confirmed", 0) + finding_counts.get("rejected", 0)
    hypothesis_counts = Counter(item.kind for item in hypotheses)
    complete_chains = sum(item.complete for item in chains)
    duplicate_groups = [item for item in correlations if item.duplicate_candidate]
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
    if surface["summary"]["out_of_scope_endpoint_count"]:
        attention_reasons.append("out_of_scope_observations")
    if validation.unresolved_finding_ids:
        attention_reasons.append("unresolved_validation")
    if consensus.blocked:
        attention_reasons.append("decision_consensus_blocked")
    if consensus.contradictory:
        attention_reasons.append("decision_signal_conflict")
    if risk.level in {"high", "critical"}:
        attention_reasons.append("campaign_risk_elevated")
    if job_statuses["failed"]:
        attention_reasons.append("failed_jobs")

    latest_event = campaign.events[-1] if campaign.events else None
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
        "campaign_risk": {
            **risk.to_dict(),
            "read_only": True,
            "advisory_only": True,
            "scope_aware": True,
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
        "finding_triage": {
            "total": len(triage),
            "highest_score": max((item.score for item in triage), default=0.0),
            "needs_validation": sum(item.recommended_state == "validate" for item in triage),
            "duplicate_review": sum(item.recommended_state == "review_duplicate" for item in triage),
            "report_review": sum(item.recommended_state == "review_for_report" for item in triage),
            "read_only": True,
        },
        "validation": {
            "graph_findings": len(validation.finding_ids),
            "attempted": len(validation.attempted_finding_ids),
            "observed_independent": len(validation.observed_independent_finding_ids),
            "unresolved": len(validation.unresolved_finding_ids),
            "unattempted": len(validation.unattempted_finding_ids),
            "all_observed_independently": validation.all_observed_independently,
        },
        "hypotheses": {
            "total": len(hypotheses),
            "by_kind": dict(sorted(hypothesis_counts.items())),
            "highest_confidence": max((item.confidence for item in hypotheses), default=0.0),
            "read_only": True,
            "scope_aware": True,
        },
        "review_queue": {
            "total": len(review_tasks),
            "highest_priority": max((item.priority for item in review_tasks), default=0.0),
            "advisory_only": True,
            "read_only": True,
            "scope_aware": True,
        },
        "red_team_decisions": {
            "total": len(decisions),
            "highest_priority": max((item.priority for item in decisions), default=0.0),
            "next_focus": decisions[0].kind if decisions else "idle",
            "blocked_from_execution": all(item.blocked_from_execution for item in decisions),
            "read_only": True,
            "scope_aware": True,
        },
        "decision_consensus": consensus.to_dict(),
        "evidence_chains": {
            "total": len(chains),
            "complete": complete_chains,
            "incomplete": len(chains) - complete_chains,
            "read_only": True,
        },
        "correlations": {
            "groups": len(correlations),
            "duplicate_groups": len(duplicate_groups),
            "findings_in_duplicate_groups": sum(len(item.finding_ids) for item in duplicate_groups),
            "auto_merge": False,
            "read_only": True,
        },
        "red_team_coverage": coverage,
        "attack_surface": {
            "summary": surface["summary"],
            "read_only": surface["read_only"],
            "scope_aware": True,
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
