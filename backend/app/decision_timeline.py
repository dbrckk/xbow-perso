from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .decision_audit import verify_decision_audit_chain
from .knowledge_memory import decision_history
from .observation_graph import load_observation_graph

router = APIRouter()


def _flatten_explanation(value: Any, prefix: str = "") -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_explanation(value[key], child))
        return flattened
    if isinstance(value, (list, tuple)):
        return {prefix: list(value)}
    return {prefix: value}


def _signal_diff(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> list[dict[str, Any]]:
    before = _flatten_explanation(previous)
    after = _flatten_explanation(current)
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old = before.get(key)
        new = after.get(key)
        if old == new:
            continue
        change: dict[str, Any] = {"signal": key, "before": old, "after": new}
        if isinstance(old, list) and isinstance(new, list):
            old_set = set(str(item) for item in old)
            new_set = set(str(item) for item in new)
            change["added"] = sorted(new_set - old_set)
            change["removed"] = sorted(old_set - new_set)
        changes.append(change)
    return changes


def _causal_summary(
    transition: dict[str, Any] | None,
    changes: list[dict[str, Any]],
) -> str | None:
    if not transition or not changes:
        return None

    by_signal = {item["signal"]: item for item in changes}
    clauses: list[str] = []

    gate_allowed = by_signal.get("gate.allowed")
    gate_blockers = by_signal.get("gate.blockers")
    if gate_allowed and gate_allowed.get("before") is True and gate_allowed.get("after") is False:
        added = list((gate_blockers or {}).get("added") or [])
        suffix = f" après {len(added)} nouveau(x) blocker(s)" if added else ""
        clauses.append(f"le gate est passé d'autorisé à bloqué{suffix}")
    elif gate_blockers and gate_blockers.get("added"):
        clauses.append(
            "de nouveaux blockers sont apparus: "
            + ", ".join(gate_blockers["added"][:3])
        )

    risk_level = by_signal.get("risk.level")
    if risk_level:
        clauses.append(
            f"le risque est passé de {risk_level.get('before')} à {risk_level.get('after')}"
        )

    consensus_focus = by_signal.get("consensus.next_focus")
    if consensus_focus:
        clauses.append(
            "le consensus a changé de "
            f"{consensus_focus.get('before')} vers {consensus_focus.get('after')}"
        )

    contradictory = by_signal.get("consensus.contradictory")
    if contradictory and contradictory.get("after") is True:
        clauses.append("une contradiction a été détectée")

    cycle_state = by_signal.get("cycle.state")
    if cycle_state:
        clauses.append(
            f"le cycle est passé de {cycle_state.get('before')} à {cycle_state.get('after')}"
        )

    surface_ready = by_signal.get("surface_enrichment.ready")
    if surface_ready:
        clauses.append(
            "la surface est devenue "
            + ("suffisamment enrichie" if surface_ready.get("after") else "insuffisamment enrichie")
        )

    coverage = by_signal.get("coverage.coverage_score")
    if coverage and isinstance(coverage.get("before"), (int, float)) and isinstance(coverage.get("after"), (int, float)):
        before = round(float(coverage["before"]) * 100)
        after = round(float(coverage["after"]) * 100)
        clauses.append(f"la couverture est passée de {before}% à {after}%")

    if not clauses:
        clauses.append(f"{len(changes)} signal(aux) décisionnel(s) ont changé")

    transition_text = (
        f"{transition.get('from_action') or '—'} → "
        f"{transition.get('to_action') or '—'}"
    )
    return transition_text + " principalement parce que " + "; ".join(clauses[:4]) + "."


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
                "why": item.metadata.get("explanation"),
            }
        )
    planner_entries.sort(
        key=lambda item: (
            item["sequence"] is None,
            int(item["sequence"] or 0),
            str(item["id"]),
        )
    )

    previous: dict[str, Any] | None = None
    for entry in planner_entries:
        if previous is None:
            entry["transition"] = None
            entry["signal_diff"] = []
            entry["causal_summary"] = None
        else:
            entry["transition"] = {
                "from_action": previous.get("action"),
                "to_action": entry.get("action"),
                "from_sequence": previous.get("sequence"),
                "to_sequence": entry.get("sequence"),
            }
            entry["signal_diff"] = _signal_diff(previous.get("why"), entry.get("why"))
            entry["causal_summary"] = _causal_summary(entry["transition"], entry["signal_diff"])
        previous = entry

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
