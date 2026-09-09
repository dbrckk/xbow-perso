from __future__ import annotations

import hashlib
import json
from urllib.parse import urlparse

from .jobqueue import JobQueue
from .main import Campaign, policy_receipt, sanitized_scan_payload
from .observation_graph import AdaptivePlanner, Observation, ObservationGraph, PlannedAction
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
    return [finding for finding in campaign.findings if f"finding:{finding.id}" not in validated]


def _enqueue_action(
    action: PlannedAction,
    campaign: Campaign,
    graph: ObservationGraph,
    queue: JobQueue,
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
        for finding in _pending_findings(campaign, graph):
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


def advance_campaign(campaign: Campaign, queue: JobQueue, store: Storage) -> dict:
    """Advance one authorized campaign toward its next bounded planner action.

    Inventory/crawl bootstrap is local-only: it records the declared primary target
    as a known asset/endpoint. Network actions are delegated only through existing
    policy-checked queue job kinds.
    """
    planner = AdaptivePlanner()

    for _ in range(3):
        graph = _load_graph(store, campaign.id)
        action = planner.plan(campaign, graph)[0]
        if action.kind == "inventory":
            _seed_primary_target(store, campaign)
            continue
        if action.kind == "crawl":
            _seed_primary_target(store, campaign)
            continue
        jobs = _enqueue_action(action, campaign, graph, queue)
        return {"action": action.to_dict(), "job_ids": [job["id"] for job in jobs]}

    graph = _load_graph(store, campaign.id)
    action = planner.plan(campaign, graph)[0]
    return {"action": action.to_dict(), "job_ids": []}
