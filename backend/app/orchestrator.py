from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse

from .agent_registry import agent_for_action
from .jobqueue import JobQueue
from .knowledge_memory import build_knowledge_snapshot, decision_history, rank_findings
from .main import Campaign, policy_receipt, sanitized_scan_payload
from .observation_graph import AdaptivePlanner, Observation, ObservationGraph, PlannedAction
from .planner_budget import PlannerBudget, apply_budget, budget_usage, validation_batch_limit
from .storage import Storage


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
    store.put_observation(
        campaign.id,
        Observation(
            id=_stable_id("endpoint", target, "planner-seed"),
            kind="endpoint",
            value=target,
            source="planner-seed",
            parent_ids=(asset_id,),
        ).to_dict(),
    )


def _pending_findings(campaign: Campaign, graph: ObservationGraph) -> list:
    finding_observations = {item.id for item in graph.by_kind("finding")}
    validated = {
        parent_id
        for validation in graph.by_kind("validation")
        for parent_id in validation.parent_ids
        if parent_id in finding_observations
    }
    pending = [finding for finding in campaign.findings if f"finding:{finding.id}" not in validated]
    priorities = {item.finding_id: item for item in rank_findings(pending, graph)}
    return sorted(
        pending,
        key=lambda finding: (-priorities[str(finding.id)].score, str(finding.id)),
    )


def _enqueue_action(
    action: PlannedAction,
    campaign: Campaign,
    graph: ObservationGraph,
    queue: JobQueue,
    *,
    validation_limit: int | None = None,
) -> list[dict]:
    fingerprint = _graph_fingerprint(graph)

    if action.kind == "scan":
        host = (urlparse(str(campaign.target.primary_url)).hostname or "").lower()
        receipt = policy_receipt(campaign, host, "automated_scan")
        if not receipt["allowed"]:
            return []
        return [
            queue.enqueue(
                campaign.id,
                "strix_scan",
                sanitized_scan_payload(campaign, receipt),
                max_attempts=2,
                dedupe_key=f"planner:scan:{fingerprint}",
            )
        ]

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
                    {"campaign_id": campaign.id, "finding_id": finding.id, "asset": finding.asset},
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
                {"campaign_id": campaign.id, "platform": "generic"},
                max_attempts=2,
                dedupe_key=f"planner:report:{fingerprint}",
            )
        ]

    return []


def _record_decision(
    store: Storage,
    campaign: Campaign,
    graph: ObservationGraph,
    action: PlannedAction,
    agent_name: str,
) -> None:
    fingerprint = _graph_fingerprint(graph)
    observation = Observation(
        id=_stable_id("decision", action.kind, fingerprint),
        kind="evidence",
        value=action.kind,
        source="orchestrator",
        metadata={
            "memory_type": "planner_decision",
            "action": action.kind,
            "agent": agent_name,
            "reason": action.reason,
            "priority": action.priority,
            "graph_fingerprint": fingerprint,
        },
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
) -> dict:
    agent = agent_for_action(action.kind)
    _record_decision(store, campaign, graph, action, agent.name)
    refreshed_graph = _load_graph(store, campaign.id)
    memory = build_knowledge_snapshot(refreshed_graph)
    usage = budget_usage(refreshed_graph, queue, campaign.id, budget)
    if action.kind == "stop" and "budget exhausted" in action.reason:
        usage = type(usage)(**{**usage.to_dict(), "exhausted": True, "reason": action.reason})
    return {
        "action": action.to_dict(),
        "agent": agent.to_dict(),
        "job_ids": [job["id"] for job in jobs],
        "memory": memory.to_dict(),
        "decision_history": decision_history(refreshed_graph),
        "budget": {"limits": budget.to_dict(), "usage": usage.to_dict()},
    }


def advance_campaign(
    campaign: Campaign,
    queue: JobQueue,
    store: Storage,
    budget: PlannerBudget | None = None,
) -> dict:
    """Advance one authorized campaign toward its next bounded planner action.

    Inventory/crawl bootstrap is local-only: it records the declared primary target
    as a known asset/endpoint. Network actions are delegated only through existing
    policy-checked queue job kinds and are attributed to a registered agent role.
    Durable queue counts and planner history cap scans, validation fan-out, reports,
    and total planner decisions so autonomous campaigns fail closed when exhausted.
    """
    planner = AdaptivePlanner()
    limits = budget or PlannerBudget()

    for _ in range(3):
        graph = _load_graph(store, campaign.id)
        action = planner.plan(campaign, graph)[0]
        action, usage = apply_budget(action, graph, queue, campaign.id, limits)
        if action.kind == "inventory":
            _seed_primary_target(store, campaign)
            continue
        if action.kind == "crawl":
            _seed_primary_target(store, campaign)
            continue
        validation_limit = validation_batch_limit(usage, limits) if action.kind == "validate" else None
        jobs = _enqueue_action(action, campaign, graph, queue, validation_limit=validation_limit)
        return _result(
            action,
            jobs,
            campaign=campaign,
            graph=graph,
            store=store,
            queue=queue,
            budget=limits,
        )

    graph = _load_graph(store, campaign.id)
    action = planner.plan(campaign, graph)[0]
    action, _ = apply_budget(action, graph, queue, campaign.id, limits)
    return _result(
        action,
        [],
        campaign=campaign,
        graph=graph,
        store=store,
        queue=queue,
        budget=limits,
    )
