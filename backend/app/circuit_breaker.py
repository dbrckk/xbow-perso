from __future__ import annotations

import hashlib
from typing import Any

from .observation_graph import Observation, ObservationGraph


_BREAKER_MEMORY_TYPE = "campaign_circuit_breaker"


def _breaker_id(reason: str) -> str:
    digest = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:24]
    return f"breaker:{digest}"


def circuit_breaker_state(graph: ObservationGraph) -> dict[str, Any]:
    events = [
        item for item in graph.by_kind("evidence")
        if item.metadata.get("memory_type") == _BREAKER_MEMORY_TYPE
    ]
    ordered = sorted(events, key=lambda item: str(item.metadata.get("at") or ""))
    if not ordered:
        return {"open": False, "reason": None, "opened_at": None, "reset_at": None}
    latest = ordered[-1]
    state = str(latest.metadata.get("state") or "")
    return {
        "open": state == "open",
        "reason": latest.metadata.get("reason") if state == "open" else None,
        "opened_at": latest.metadata.get("at") if state == "open" else None,
        "reset_at": latest.metadata.get("at") if state == "reset" else None,
    }


def record_circuit_open(store: Any, campaign_id: str, reason: str, *, at: str) -> dict[str, Any]:
    graph = ObservationGraph.from_records(store.list_observations(campaign_id))
    current = circuit_breaker_state(graph)
    if current["open"]:
        return current
    observation = Observation(
        id=_breaker_id(f"open:{reason}:{at}"),
        kind="evidence",
        value="open",
        source="orchestrator",
        metadata={
            "memory_type": _BREAKER_MEMORY_TYPE,
            "state": "open",
            "reason": reason,
            "at": at,
            "operator_reset_required": True,
        },
    )
    store.put_observation(campaign_id, observation.to_dict())
    return {"open": True, "reason": reason, "opened_at": at, "reset_at": None}


def record_circuit_reset(store: Any, campaign_id: str, *, at: str) -> dict[str, Any]:
    graph = ObservationGraph.from_records(store.list_observations(campaign_id))
    current = circuit_breaker_state(graph)
    if not current["open"]:
        return current
    observation = Observation(
        id=_breaker_id(f"reset:{current['opened_at']}:{at}"),
        kind="evidence",
        value="reset",
        source="operator",
        metadata={
            "memory_type": _BREAKER_MEMORY_TYPE,
            "state": "reset",
            "at": at,
            "operator_reset": True,
        },
    )
    store.put_observation(campaign_id, observation.to_dict())
    return {"open": False, "reason": None, "opened_at": None, "reset_at": at}
