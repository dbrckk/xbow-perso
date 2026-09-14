from types import SimpleNamespace

from app.decision_timeline import build_decision_timeline
from app.main import app
from app.observation_graph import Observation, ObservationGraph


def _campaign():
    return SimpleNamespace(
        events=[
            {
                "type": "finding_received",
                "finding_id": "f1",
                "at": "2026-09-14T07:00:01+00:00",
            },
            {
                "type": "validation_queued",
                "finding_id": "f1",
                "job_id": "job-1",
                "at": "2026-09-14T07:00:03+00:00",
            },
        ]
    )


def _graph():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "decision:1",
            "evidence",
            "scan",
            "orchestrator",
            metadata={
                "memory_type": "planner_decision",
                "action": "scan",
                "agent": "analysis-agent",
                "reason": "fixture",
                "priority": 80,
                "graph_fingerprint": "g1",
                "at": "2026-09-14T07:00:00+00:00",
                "audit_seq": 1,
                "previous_decision_hash": None,
                "decision_hash": "legacy-fixture",
            },
        )
    )
    return graph


def test_decision_timeline_combines_timestamped_planner_and_campaign_events(monkeypatch):
    graph = _graph()
    monkeypatch.setattr(
        "app.decision_timeline.verify_decision_audit_chain",
        lambda _graph: {
            "valid": True,
            "checked": 1,
            "sealed_decisions": 1,
            "legacy_unsealed": [],
            "reason": None,
        },
    )

    result = build_decision_timeline(_campaign(), graph)

    assert [item["type"] for item in result["timeline"]] == [
        "planner_decision",
        "campaign_event",
        "campaign_event",
    ]
    assert result["timeline"][0]["action"] == "scan"
    assert result["timeline"][1]["event_type"] == "finding_received"
    assert result["timeline"][2]["event_type"] == "validation_queued"
    assert result["summary"]["planner_decisions"] == 1
    assert result["summary"]["campaign_events"] == 2
    assert result["audit"]["valid"] is True


def test_decision_timeline_keeps_un_timestamped_legacy_decisions_out_of_merged_timeline(monkeypatch):
    graph = _graph()
    item = graph._items["decision:1"]
    item.metadata.pop("at")
    monkeypatch.setattr(
        "app.decision_timeline.verify_decision_audit_chain",
        lambda _graph: {
            "valid": True,
            "checked": 1,
            "sealed_decisions": 1,
            "legacy_unsealed": [],
            "reason": None,
        },
    )

    result = build_decision_timeline(_campaign(), graph)

    assert len(result["planner_decisions"]) == 1
    assert all(item["type"] == "campaign_event" for item in result["timeline"])


def test_decision_timeline_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/decision-timeline" in app.openapi()["paths"]



def test_decision_timeline_exposes_historical_why_snapshot(monkeypatch):
    graph = _graph()
    graph._items["decision:1"].metadata["explanation"] = {
        "gate": {"allowed": False, "blockers": ["failed_jobs"], "reason": "blocked"},
        "risk": {"score": 0.8, "level": "high", "blocked": True, "reasons": ["risk"]},
        "consensus": {
            "next_focus": "review_contradiction",
            "confidence": 1.0,
            "blocked": True,
            "contradictory": True,
            "reasons": ["human review"],
            "supporting_kinds": ["review_contradiction"],
        },
        "cycle": {
            "state": "halt",
            "next_action": "stop",
            "reason": "human review",
            "safe_to_progress": False,
        },
        "surface_enrichment": {"score": 0.5, "threshold": 0.4, "ready": True},
        "coverage": {"coverage_score": 0.6, "interpretation": "evidence"},
    }
    monkeypatch.setattr(
        "app.decision_timeline.verify_decision_audit_chain",
        lambda _graph: {
            "valid": True,
            "checked": 1,
            "sealed_decisions": 1,
            "legacy_unsealed": [],
            "reason": None,
        },
    )

    result = build_decision_timeline(_campaign(), graph)

    why = result["planner_decisions"][0]["why"]
    assert why["gate"]["allowed"] is False
    assert why["gate"]["blockers"] == ["failed_jobs"]
    assert why["consensus"]["contradictory"] is True
    assert why["cycle"]["state"] == "halt"
