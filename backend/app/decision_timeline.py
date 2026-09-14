from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .decision_audit import verify_decision_audit_chain
from .knowledge_memory import decision_history
from .observation_graph import load_observation_graph

router = APIRouter()


def build_decision_timeline(
    campaign: Any,
    graph: Any,
) -> dict[str, Any]:
    planner_entries = []
    for item in graph.by_kind("evidence"):
        if item.metadata.get("memory_type") != "planner_decision":
            continue
        planner_entries.append(
            {
                "type": "planner_decision",
                "id": item.id,
                "at": item.metadata.get("at"),
                "sequence": item.metadata.get("audit_seq"),
                "action": item.metadata.get("action"),
                "agent": item.metadata.get("agent"),
                "reason": item.metadata.get("reason"),
                "priority": item.metadata.get("priority"),
                "decision_hash": item.metadata.get("decision_hash"),
                "previous_decision_hash": item.metadata.get("previous_decision_hash"),
                "signed": bool(item.metadata.get("decision_signature")),
            }
        )
    planner_entries.sort(
        key=lambda item: (
            item["sequence"] is None,
            int(item["sequence"] or 0),
            str(item["id"]),
        )
    )

    campaign_entries = []
    for index, event in enumerate(campaign.events):
        campaign_entries.append(
            {
                "type": "campaign_event",
                "id": f"campaign-event:{index}",
                "at": event.get("at"),
                "sequence": index + 1,
                "event_type": event.get("type"),
                "finding_id": event.get("finding_id"),
                "job_id": event.get("job_id") or event.get("report_job_id"),
                "confirmed": event.get("confirmed"),
                "validator": event.get("validator"),
                "request_id": event.get("request_id"),
            }
        )

    timestamped = [
        item
        for item in (*planner_entries, *campaign_entries)
        if item.get("at")
    ]
    timestamped.sort(
        key=lambda item: (
            str(item.get("at")),
            0 if item["type"] == "planner_decision" else 1,
            str(item.get("id")),
        )
    )

    return {
        "timeline": timestamped,
        "planner_decisions": planner_entries,
        "campaign_events": campaign_entries,
        "audit": verify_decision_audit_chain(graph),
        "legacy_decision_history": decision_history(graph),
        "summary": {
            "timeline_entries": len(timestamped),
            "planner_decisions": len(planner_entries),
            "campaign_events": len(campaign_entries),
        },
    }


@router.get("/api/campaigns/{campaign_id}/decision-timeline")
def campaign_decision_timeline(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    payload = build_decision_timeline(campaign, graph)
    return {
        "campaign_id": campaign.id,
        **payload,
        "read_only": True,
        "audit_only": True,
    }
