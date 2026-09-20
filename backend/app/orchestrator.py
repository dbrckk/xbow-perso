from __future__ import annotations

import hashlib
import json
import math
import os
from urllib.parse import urlparse

from .adaptive_cycle import build_adaptive_cycle
from .attack_surface import build_attack_surface
from .agent_registry import agent_for_action
from .autonomy_gate import build_autonomy_gate
from .campaign_risk import build_campaign_risk
from .campaign_runtime import CampaignRuntimeLimit, campaign_runtime_limit_from_env, runtime_status
from .circuit_breaker import circuit_breaker_state, record_circuit_open
from .coverage import build_coverage_guidance, build_evidence_coverage
from .decision_audit import next_audit_link, seal_decision_metadata
from .decision_consensus import build_decision_consensus
from .decision_timeline import planner_stability_breaker_reason, planner_stability_from_graph
from .evidence_quality import build_evidence_quality
from .finding_correlation import cluster_findings
from .hypothesis_memory import build_hypotheses
from .job_provenance import attach_job_provenance
from .jobqueue import JobQueue
from .knowledge_memory import build_knowledge_snapshot, decision_history, rank_findings
from .learning_memory import build_learning_memory, summarize_worker_outcomes
from .main import Campaign, is_host_allowed, policy_receipt, sanitized_scan_payload, utcnow
from .observation_graph import AdaptivePlanner, Observation, ObservationGraph, PlannedAction
from .planner_budget import PlannerBudget, apply_budget, budget_usage, planner_budget_from_env
from .pipeline_swarm import coordinate_pipeline_action
from .recon_priority import prioritize_recon_tasks
from .recon_swarm import build_recon_plan
from .red_team_decision import build_red_team_decisions
from .surface_diff import build_surface_diff_intelligence
from .surface_temporal import build_temporal_surface_profile
from .target_memory import build_target_memory
from .scanner_adaptation import adapt_scanner_engines
from .storage import Storage
from .swarm_coordinator import coordinate_recon_swarm
from .validation_state import observed_independent_finding_ids


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _graph_fingerprint(graph: ObservationGraph) -> str:
    payload = [
        {
            "id": item.id,
            "kind": item.kind,
            "value": item.value,
            "source": item.source,
            "parent_ids": item.parent_ids,
            "metadata": item.metadata,
        }
        for item in sorted(graph.values(), key=lambda item: item.id)
        if item.metadata.get("memory_type") != "planner_decision"
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def _load_graph(store: Storage, campaign_id: str) -> ObservationGraph:
    return ObservationGraph.from_records(store.list_observations(campaign_id))


def _seed_primary_target(store: Storage, campaign: Campaign) -> None:
    target = str(campaign.target.primary_url)
    host = (urlparse(target).hostname or "").lower()
    if not host:
        return
    asset_id = _stable_id("asset", host, "planner-seed")
    store.put_observation(
        campaign.id,
        Observation(
            id=asset_id,
            kind="asset",
            value=host,
            source="planner-seed",
        ).to_dict(),
    )


def _minimum_enrichment_score() -> float:
    raw = os.getenv("XBOW_MIN_RECON_ENRICHMENT_SCORE", "0.40")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("XBOW_MIN_RECON_ENRICHMENT_SCORE must be a number") from exc
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("XBOW_MIN_RECON_ENRICHMENT_SCORE must be between 0 and 1")
    return value


def _surface_enrichment(
    campaign: Campaign,
    graph: ObservationGraph,
) -> dict:
    rules = campaign.target.rules
    surface = build_attack_surface(
        graph,
        scope_checker=lambda host: is_host_allowed(
            host,
            rules.allowed_targets,
            rules.denied_targets,
        ),
    )
    score = float(surface["summary"]["enrichment_score"])
    threshold = _minimum_enrichment_score()
    return {
        "score": score,
        "threshold": threshold,
        "ready": score >= threshold,
        "source_diversity": int(surface["summary"]["source_diversity"]),
        "surface_sources": list(surface["summary"]["surface_sources"]),
    }


def _intelligence_context(
    campaign: Campaign,
    graph: ObservationGraph,
    queue: JobQueue,
    store: Storage,
    budget: PlannerBudget,
    runtime: object,
    planned_actions: list[PlannedAction],
) -> dict:
    rules = campaign.target.rules

    def scope_checker(host: str) -> bool:
        return is_host_allowed(host, rules.allowed_targets, rules.denied_targets)

    decisions = build_red_team_decisions(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
        hypothesis_snapshots=store.list_hypothesis_snapshots(campaign.id, limit=50),
        limit=10,
    )
    consensus = build_decision_consensus(decisions)
    risk = build_campaign_risk(
        campaign.findings,
        graph,
        scope_checker=scope_checker,
    )
    usage = budget_usage(graph, queue, campaign.id, budget)
    job_statuses = queue.campaign_job_status_counts(campaign.id)
    gate = build_autonomy_gate(
        automated_scanning=rules.automated_scanning,
        destructive_testing=rules.destructive_testing,
        denial_of_service=rules.denial_of_service,
        social_engineering=rules.social_engineering,
        credential_attacks=rules.credential_attacks,
        runtime_exhausted=bool(getattr(runtime, "exhausted", False)),
        budget_blocked=bool(usage.blocked_actions),
        failed_jobs=job_statuses["failed"],
        risk=risk,
        consensus=consensus,
    )
    memories = build_learning_memory(graph)
    worker_outcomes = summarize_worker_outcomes(campaign.events)
    cycle = build_adaptive_cycle(gate, planned_actions, memories, worker_outcomes)
    recon_plan = build_recon_plan(
        str(campaign.target.primary_url),
        graph,
        scope_checker=scope_checker,
        limit=10,
    )
    campaign_doc = campaign.model_dump(mode="json")
    target_memory = build_target_memory(store, campaign_doc)
    surface_diff = build_surface_diff_intelligence(target_memory)
    surface_temporal = build_temporal_surface_profile(store, campaign_doc)
    recon_priority = prioritize_recon_tasks(
        recon_plan,
        surface_diff,
        target_memory,
        surface_temporal,
    )
    swarm = coordinate_recon_swarm(list(recon_priority.tasks))
    coverage = build_evidence_coverage(graph, scope_checker=scope_checker)
    coverage_guidance = build_coverage_guidance(coverage)
    scanner_adaptation = adapt_scanner_engines(
        _scan_engines(),
        memories,
        worker_outcomes,
    )
    return {
        "decisions": decisions,
        "consensus": consensus,
        "risk": risk,
        "gate": gate,
        "memory": memories,
        "worker_outcomes": worker_outcomes,
        "cycle": cycle,
        "recon": list(swarm.tasks),
        "recon_priority": recon_priority,
        "surface_diff": surface_diff,
        "surface_temporal": surface_temporal,
        "swarm": swarm,
        "coverage": coverage,
        "coverage_guidance": coverage_guidance,
        "scanner_adaptation": scanner_adaptation,
        "surface_enrichment": _surface_enrichment(campaign, graph),
    }


def _validation_saturated_cluster_ids(
    campaign: Campaign,
    graph: ObservationGraph,
) -> set[str]:
    """Return clusters whose validated representative has strong independent evidence.

    This only suppresses additional automatic validation fan-out. It never marks
    sibling findings as validated, confirmed, or report-ready.
    """
    clusters, _similarities = cluster_findings(campaign.findings, threshold=0.75)
    if not clusters:
        return set()

    quality_by_id = {
        item.finding_id: item
        for item in build_evidence_quality(graph)
    }
    observed_validated = {
        item.removeprefix("finding:")
        for item in observed_independent_finding_ids(graph)
    }

    saturated: set[str] = set()
    for cluster in clusters:
        if cluster.confidence < 0.90:
            continue
        for finding_id in cluster.finding_ids:
            quality = quality_by_id.get(finding_id)
            if (
                finding_id in observed_validated
                and quality is not None
                and quality.grade == "high"
                and quality.integrity_attested
                and quality.corroborated
            ):
                saturated.add(cluster.cluster_id)
                break
    return saturated


def _pending_findings(campaign: Campaign, graph: ObservationGraph) -> list:
    observed_validated = observed_independent_finding_ids(graph)
    pending = [
        finding
        for finding in campaign.findings
        if f"finding:{finding.id}" not in observed_validated
    ]
    priorities = {item.finding_id: item for item in rank_findings(pending, graph)}
    hypotheses = {item.finding_id: item for item in build_hypotheses(graph)}
    ordered = sorted(
        pending,
        key=lambda finding: (
            -priorities[str(finding.id)].score,
            hypotheses.get(str(finding.id)).confidence
            if hypotheses.get(str(finding.id)) is not None
            else 0.0,
            str(finding.id),
        ),
    )

    # Validate only one representative from each high-confidence duplicate cluster
    # per planner cycle. After that representative is independently observed, the
    # next campaign advance re-evaluates the graph and may select another member.
    clusters, _similarities = cluster_findings(campaign.findings, threshold=0.75)
    cluster_by_member = {
        finding_id: cluster.cluster_id
        for cluster in clusters
        for finding_id in cluster.finding_ids
    }
    selected_clusters: set[str] = set()
    saturated_clusters = _validation_saturated_cluster_ids(campaign, graph)
    selected: list = []
    for finding in ordered:
        cluster_id = cluster_by_member.get(str(finding.id))
        if cluster_id is None:
            selected.append(finding)
            continue
        if cluster_id in saturated_clusters:
            continue
        if cluster_id in selected_clusters:
            continue
        selected_clusters.add(cluster_id)
        selected.append(finding)
    return selected


def _enqueue_recon_tasks(
    campaign: Campaign,
    graph: ObservationGraph,
    queue: JobQueue,
    tasks: list,
) -> list[dict]:
    fingerprint = _graph_fingerprint(graph)
    jobs: list[dict] = []
    for task in tasks:
        if task.kind == "browser_observe":
            jobs.append(
                queue.enqueue(
                    campaign.id,
                    "browser_flow",
                    attach_job_provenance(
                        {
                            "campaign_id": campaign.id,
                            "steps": [
                                {
                                    "operation": "navigate",
                                    "url": task.target,
                                    "timeout_ms": 10000,
                                },
                                {
                                    "operation": "screenshot",
                                    "timeout_ms": 10000,
                                },
                            ],
                        },
                        campaign,
                        job_kind="browser_flow",
                        action="crawl",
                    ),
                    max_attempts=2,
                    dedupe_key=f"recon:browser:{fingerprint}:{task.target}",
                )
            )
            continue
        jobs.append(
            queue.enqueue(
                campaign.id,
                "recon_task",
                attach_job_provenance(
                    {
                        "campaign_id": campaign.id,
                        "kind": task.kind,
                        "target": task.target,
                        "max_requests": task.max_requests,
                        "allowed_methods": list(task.allowed_methods),
                        "same_origin_only": task.same_origin_only,
                    },
                    campaign,
                    job_kind="recon_task",
                    action="crawl",
                ),
                max_attempts=2,
                dedupe_key=f"recon:{task.kind}:{fingerprint}:{task.target}",
            )
        )
    return jobs


def _scan_engines() -> tuple[str, ...]:
    raw = os.getenv("XBOW_SCAN_ENGINES", "strix")
    values = tuple(dict.fromkeys(part.strip().lower() for part in raw.split(",") if part.strip()))
    if not values:
        raise ValueError("XBOW_SCAN_ENGINES must include at least one scanner engine")
    unsupported = [value for value in values if value not in {"strix", "nuclei"}]
    if unsupported:
        raise ValueError(f"unsupported scanner engine: {unsupported[0]}")
    return values


def _enqueue_action(
    action: PlannedAction,
    campaign: Campaign,
    graph: ObservationGraph,
    queue: JobQueue,
    *,
    validation_limit: int | None = None,
    scan_engines: tuple[str, ...] | None = None,
) -> list[dict]:
    fingerprint = _graph_fingerprint(graph)

    if action.kind == "scan":
        host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
        receipt = policy_receipt(campaign, host, "automated_scan")
        if not receipt["allowed"]:
            return []
        stable_receipt = {key: value for key, value in receipt.items() if key != "timestamp"}
        jobs = []
        engines = scan_engines if scan_engines is not None else _scan_engines()
        for engine in engines:
            kind = "strix_scan" if engine == "strix" else "nuclei_scan"
            payload = sanitized_scan_payload(
                campaign,
                stable_receipt,
                job_kind=kind,
            )
            jobs.append(
                queue.enqueue(
                    campaign.id,
                    kind,
                    payload,
                    max_attempts=2,
                    dedupe_key=(f"planner:scan:{fingerprint}" if engine == "strix" else f"planner:scan:nuclei:{fingerprint}"),
                )
            )
        return jobs

    if action.kind == "validate":
        jobs = []
        pending = _pending_findings(campaign, graph)
        if validation_limit is not None:
            pending = pending[:validation_limit]
        for finding in pending:
            jobs.append(
                queue.enqueue(
                    campaign.id,
                    "independent_validation",
                    attach_job_provenance(
                        {"campaign_id": campaign.id, "finding_id": finding.id, "asset": finding.asset},
                        campaign,
                        job_kind="independent_validation",
                        action="validate",
                    ),
                    max_attempts=2,
                    dedupe_key=f"validation:{finding.id}",
                )
            )
        return jobs

    if action.kind == "report":
        return [
            queue.enqueue(
                campaign.id,
                "report",
                attach_job_provenance(
                    {"campaign_id": campaign.id, "platform": "generic"},
                    campaign,
                    job_kind="report",
                    action="report",
                ),
                max_attempts=2,
                dedupe_key=f"planner:report:{fingerprint}",
            )
        ]

    return []


def _decision_explanation(intelligence: dict | None) -> dict | None:
    if intelligence is None:
        return None
    gate = intelligence["gate"].to_dict()
    risk = intelligence["risk"].to_dict()
    consensus = intelligence["consensus"].to_dict()
    cycle = intelligence["cycle"].to_dict()
    surface = dict(intelligence["surface_enrichment"])
    coverage = dict(intelligence["coverage"])
    return {
        "gate": {
            "allowed": gate.get("allowed"),
            "blockers": list(gate.get("blockers") or []),
            "reason": gate.get("reason"),
        },
        "risk": {
            "score": risk.get("score"),
            "level": risk.get("level"),
            "blocked": risk.get("blocked"),
            "reasons": list(risk.get("reasons") or []),
        },
        "consensus": {
            "next_focus": consensus.get("next_focus"),
            "confidence": consensus.get("confidence"),
            "blocked": consensus.get("blocked"),
            "contradictory": consensus.get("contradictory"),
            "reasons": list(consensus.get("reasons") or []),
            "supporting_kinds": list(consensus.get("supporting_kinds") or []),
        },
        "cycle": {
            "state": cycle.get("state"),
            "next_action": cycle.get("next_action"),
            "reason": cycle.get("reason"),
            "safe_to_progress": cycle.get("safe_to_progress"),
        },
        "surface_enrichment": {
            "score": surface.get("score"),
            "threshold": surface.get("threshold"),
            "ready": surface.get("ready"),
        },
        "coverage": {
            "coverage_score": coverage.get("coverage_score"),
            "interpretation": coverage.get("interpretation"),
        },
    }


def _record_decision(
    store: Storage,
    campaign: Campaign,
    graph: ObservationGraph,
    action: PlannedAction,
    agent_name: str,
    intelligence: dict | None = None,
) -> None:
    fingerprint = _graph_fingerprint(graph)
    observation_id = _stable_id("decision", action.kind, action.reason, fingerprint)
    if any(
        item.id == observation_id
        and item.metadata.get("memory_type") == "planner_decision"
        for item in graph.by_kind("evidence")
    ):
        return
    audit_seq, previous_hash = next_audit_link(graph)
    explanation = _decision_explanation(intelligence)
    metadata = seal_decision_metadata(
        observation_id,
        {
            "memory_type": "planner_decision",
            "action": action.kind,
            "agent": agent_name,
            "reason": action.reason,
            "priority": action.priority,
            "graph_fingerprint": fingerprint,
            "at": utcnow(),
            "audit_seq": audit_seq,
            "previous_decision_hash": previous_hash,
            "explanation": explanation,
        },
    )
    observation = Observation(
        id=observation_id,
        kind="evidence",
        value=action.kind,
        source="orchestrator",
        metadata=metadata,
    )
    store.put_observation(campaign.id, observation.to_dict())


def _result(
    action: PlannedAction,
    jobs: list[dict],
    *,
    campaign: Campaign,
    graph: ObservationGraph,
    store: Storage,
    queue: JobQueue,
    budget: PlannerBudget,
    intelligence: dict | None = None,
) -> dict:
    agent = agent_for_action(action.kind)
    _record_decision(store, campaign, graph, action, agent.name, intelligence)
    refreshed_graph = _load_graph(store, campaign.id)
    hypotheses = build_hypotheses(refreshed_graph)
    if hypotheses:
        store.put_hypothesis_snapshot(
            campaign.id,
            hypotheses[0].graph_fingerprint,
            [item.to_dict() for item in hypotheses],
        )
    memory = build_knowledge_snapshot(refreshed_graph)
    usage = budget_usage(refreshed_graph, queue, campaign.id, budget)
    if action.kind == "stop" and "budget exhausted" in action.reason:
        usage = type(usage)(**{**usage.to_dict(), "exhausted": True, "reason": action.reason})
    intelligence_payload = None
    if intelligence is not None:
        intelligence_payload = {
            "cycle": intelligence["cycle"].to_dict(),
            "gate": intelligence["gate"].to_dict(),
            "risk": intelligence["risk"].to_dict(),
            "consensus": intelligence["consensus"].to_dict(),
            "decisions": [item.to_dict() for item in intelligence["decisions"]],
            "learning_memory": [item.to_dict() for item in intelligence["memory"]],
            "worker_outcomes": dict(intelligence["worker_outcomes"]),
            "recon_plan": [item.to_dict() for item in intelligence["recon"]],
            "recon_priority": intelligence["recon_priority"].to_dict(),
            "surface_diff": dict(intelligence["surface_diff"]),
            "surface_temporal": dict(intelligence["surface_temporal"]),
            "swarm_coordination": intelligence["swarm"].to_dict(),
            "coverage": dict(intelligence["coverage"]),
            "coverage_guidance": dict(intelligence["coverage_guidance"]),
            "scanner_adaptation": intelligence["scanner_adaptation"].to_dict(),
            "pipeline_coordination": (
                intelligence["pipeline_coordination"].to_dict()
                if intelligence.get("pipeline_coordination") is not None
                else None
            ),
            "surface_enrichment": dict(intelligence["surface_enrichment"]),
            "read_only_context": True,
        }
    return {
        "action": action.to_dict(),
        "agent": agent.to_dict(),
        "job_ids": [job["id"] for job in jobs],
        "memory": memory.to_dict(),
        "hypotheses": [item.to_dict() for item in hypotheses],
        "decision_history": decision_history(refreshed_graph),
        "budget": {"limits": budget.to_dict(), "usage": usage.to_dict()},
        "intelligence": intelligence_payload,
    }


def advance_campaign(
    campaign: Campaign,
    queue: JobQueue,
    store: Storage,
    budget: PlannerBudget | None = None,
    runtime_limit: CampaignRuntimeLimit | None = None,
) -> dict:
    """Advance one authorized campaign toward its next bounded planner action.

    Inventory/crawl bootstrap is local-only: it records the declared primary target
    as a known asset/endpoint. Network actions are delegated only through existing
    policy-checked queue job kinds and are attributed to a registered agent role.
    Durable queue counts and planner history cap scans, validation fan-out, reports,
    total planner decisions, and wall-clock runtime so autonomous campaigns fail
    closed when any configured budget is exhausted.
    """
    planner = AdaptivePlanner()
    initial_graph = _load_graph(store, campaign.id)
    breaker = circuit_breaker_state(initial_graph)
    if breaker["open"]:
        return _result(
            PlannedAction("stop", str(campaign.target.primary_url), f"circuit breaker open: {breaker['reason']}", 100),
            [], campaign=campaign, graph=initial_graph, store=store, queue=queue,
            budget=(budget if budget is not None else planner_budget_from_env()), intelligence=None,
        )

    stability = planner_stability_from_graph(initial_graph)
    stability_reason = planner_stability_breaker_reason(stability)
    if stability_reason:
        record_circuit_open(store, campaign.id, stability_reason, at=utcnow())
        return _result(
            PlannedAction(
                "stop",
                str(campaign.target.primary_url),
                stability_reason,
                100,
            ),
            [],
            campaign=campaign,
            graph=initial_graph,
            store=store,
            queue=queue,
            budget=(budget if budget is not None else planner_budget_from_env()),
            intelligence=None,
        )

    limits = budget if budget is not None else planner_budget_from_env()
    effective_runtime_limit = (
        runtime_limit if runtime_limit is not None else campaign_runtime_limit_from_env()
    )
    runtime = runtime_status(campaign.created_at, effective_runtime_limit)
    if runtime.exhausted:
        graph = _load_graph(store, campaign.id)
        record_circuit_open(store, campaign.id, runtime.reason or "campaign runtime budget exhausted", at=utcnow())
        return _result(
            PlannedAction("stop", str(campaign.target.primary_url), runtime.reason or "campaign runtime budget exhausted", 100),
            [],
            campaign=campaign,
            graph=graph,
            store=store,
            queue=queue,
            budget=limits,
            intelligence=None,
        )

    for _ in range(3):
        graph = _load_graph(store, campaign.id)
        planned_actions = planner.plan(campaign, graph)
        action = planned_actions[0]
        action, usage = apply_budget(action, graph, queue, campaign.id, limits)
        if usage.exhausted and action.kind == "stop":
            record_circuit_open(store, campaign.id, action.reason, at=utcnow())
        runtime = runtime_status(campaign.created_at, effective_runtime_limit)
        intelligence = _intelligence_context(
            campaign,
            graph,
            queue,
            store,
            limits,
            runtime,
            [action],
        )
        cycle = intelligence["cycle"]

        if cycle.next_action == "stop" or not cycle.safe_to_progress:
            breaker_blockers = {"failed_jobs", "runtime_exhausted", "budget_blocked", "campaign_risk_blocked"}
            if breaker_blockers.intersection(set(intelligence["gate"].blockers)):
                record_circuit_open(store, campaign.id, cycle.reason, at=utcnow())
            stop_reason = cycle.reason
            if cycle.requires_human:
                stop_reason = f"human review required: {cycle.reason}"
            stop_action = PlannedAction(
                "stop",
                str(campaign.target.primary_url),
                stop_reason,
                100,
            )
            return _result(
                stop_action,
                [],
                campaign=campaign,
                graph=graph,
                store=store,
                queue=queue,
                budget=limits,
                intelligence=intelligence,
            )

        if action.kind == "inventory":
            _seed_primary_target(store, campaign)
            continue
        if action.kind == "crawl":
            recon_jobs = _enqueue_recon_tasks(
                campaign,
                graph,
                queue,
                intelligence["recon"],
            )
            return _result(
                action,
                recon_jobs,
                campaign=campaign,
                graph=graph,
                store=store,
                queue=queue,
                budget=limits,
                intelligence=intelligence,
            )
        if action.kind == "scan" and not intelligence["surface_enrichment"]["ready"]:
            recon_jobs = _enqueue_recon_tasks(
                campaign,
                graph,
                queue,
                intelligence["recon"],
            )
            enrichment = intelligence["surface_enrichment"]
            recon_action = PlannedAction(
                "crawl",
                str(campaign.target.primary_url),
                (
                    "attack surface enrichment below scan threshold "
                    f"({enrichment['score']:.4f} < {enrichment['threshold']:.4f})"
                ),
                95,
            )
            return _result(
                recon_action,
                recon_jobs,
                campaign=campaign,
                graph=graph,
                store=store,
                queue=queue,
                budget=limits,
                intelligence=intelligence,
            )
        validation_limit = None
        scan_engines = None
        if action.kind == "scan":
            selected = intelligence["scanner_adaptation"].selected_engines
            coordination = coordinate_pipeline_action(
                "scan",
                len(selected),
                usage,
                limits,
            )
            scan_engines = selected[:coordination.allocated_items]
            intelligence["pipeline_coordination"] = coordination
        elif action.kind == "validate":
            pending_count = len(_pending_findings(campaign, graph))
            coordination = coordinate_pipeline_action(
                "validate",
                pending_count,
                usage,
                limits,
            )
            validation_limit = coordination.allocated_items
            intelligence["pipeline_coordination"] = coordination
        elif action.kind == "report":
            coordination = coordinate_pipeline_action(
                "report",
                1,
                usage,
                limits,
            )
            intelligence["pipeline_coordination"] = coordination
        jobs = _enqueue_action(
            action,
            campaign,
            graph,
            queue,
            validation_limit=validation_limit,
            scan_engines=scan_engines,
        )
        if action.kind == "validate" and not jobs:
            action = PlannedAction(
                "stop",
                str(campaign.target.primary_url),
                "cluster validation saturated by strong representative evidence",
                100,
            )
        return _result(
            action,
            jobs,
            campaign=campaign,
            graph=graph,
            store=store,
            queue=queue,
            budget=limits,
            intelligence=intelligence,
        )

    graph = _load_graph(store, campaign.id)
    action = planner.plan(campaign, graph)[0]
    action, _ = apply_budget(action, graph, queue, campaign.id, limits)
    runtime = runtime_status(campaign.created_at, effective_runtime_limit)
    intelligence = _intelligence_context(
        campaign,
        graph,
        queue,
        store,
        limits,
        runtime,
        [action],
    )
    return _result(
        action,
        [],
        campaign=campaign,
        graph=graph,
        store=store,
        queue=queue,
        budget=limits,
        intelligence=intelligence,
    )
