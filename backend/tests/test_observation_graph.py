from types import SimpleNamespace

import pytest

from app.observation_graph import AdaptivePlanner, Observation, ObservationGraph


def campaign(*, automated_scanning=True):
    return SimpleNamespace(
        target=SimpleNamespace(
            primary_url="https://example.com",
            rules=SimpleNamespace(automated_scanning=automated_scanning),
        )
    )


def test_graph_rejects_unknown_parent():
    graph = ObservationGraph()
    with pytest.raises(ValueError, match="unknown parent"):
        graph.add(Observation("e1", "endpoint", "/api", "test", parent_ids=("missing",)))


def test_graph_restores_without_relying_on_row_order():
    graph = ObservationGraph.from_records(
        [
            {"id": "e1", "kind": "endpoint", "value": "/api", "source": "crawler", "parent_ids": ("a1",)},
            {"id": "a1", "kind": "asset", "value": "example.com", "source": "scope"},
        ]
    )
    assert [item.id for item in graph.by_kind("asset")] == ["a1"]
    assert [item.id for item in graph.by_kind("endpoint")] == ["e1"]


def test_graph_restore_rejects_missing_or_cyclic_parents():
    with pytest.raises(ValueError, match="missing or cyclic"):
        ObservationGraph.from_records(
            [{"id": "e1", "kind": "endpoint", "value": "/api", "source": "crawler", "parent_ids": ("missing",)}]
        )


def test_planner_starts_with_inventory():
    actions = AdaptivePlanner().plan(campaign(), ObservationGraph())
    assert actions[0].kind == "inventory"


def test_planner_progresses_through_bounded_phases():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.com", "recon"))
    assert AdaptivePlanner().plan(campaign(), graph)[0].kind == "crawl"

    graph.add(Observation("e1", "endpoint", "/api", "crawler", parent_ids=("a1",)))
    assert AdaptivePlanner().plan(campaign(), graph)[0].kind == "scan"

    graph.add(Observation("f1", "finding", "candidate", "scanner", parent_ids=("e1",)))
    assert AdaptivePlanner().plan(campaign(), graph)[0].kind == "validate"

    graph.add(Observation("v1", "validation", "observed", "validator", parent_ids=("f1",)))
    assert AdaptivePlanner().plan(campaign(), graph)[0].kind == "report"

    graph.add(
        Observation(
            "r1",
            "evidence",
            "report-artifact",
            "report-engine",
            metadata={"artifact_kind": "report"},
        )
    )
    assert AdaptivePlanner().plan(campaign(), graph)[0].kind == "stop"


def test_planner_stops_after_completed_scan_without_findings():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.com", "scope"))
    graph.add(Observation("e1", "endpoint", "https://example.com", "scope", parent_ids=("a1",)))
    graph.add(
        Observation(
            "scan:j1",
            "evidence",
            "completed",
            "strix",
            parent_ids=("e1",),
            metadata={"phase": "scan", "status": "completed", "findings": 0},
        )
    )
    action = AdaptivePlanner().plan(campaign(), graph)[0]
    assert action.kind == "stop"
    assert "without recorded findings" in action.reason


def test_planner_counts_validations_by_finding_relationship():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.com", "recon"))
    graph.add(Observation("e1", "endpoint", "/api", "crawler", parent_ids=("a1",)))
    graph.add(Observation("f1", "finding", "first", "scanner", parent_ids=("e1",)))
    graph.add(Observation("f2", "finding", "second", "scanner", parent_ids=("e1",)))
    graph.add(Observation("v1", "validation", "one", "validator-a", parent_ids=("f1",)))
    graph.add(Observation("v2", "validation", "two", "validator-b", parent_ids=("f1",)))
    assert AdaptivePlanner().plan(campaign(), graph)[0].kind == "validate"


def test_planner_stops_when_automation_is_disabled():
    graph = ObservationGraph()
    action = AdaptivePlanner().plan(campaign(automated_scanning=False), graph)[0]
    assert action.kind == "stop"
    assert "disabled" in action.reason
