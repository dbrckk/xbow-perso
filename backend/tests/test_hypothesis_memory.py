from app.hypothesis_memory import (
    build_hypotheses,
    diff_hypothesis_snapshots,
    hypothesis_snapshot_is_current,
    summarize_hypothesis_stability,
)
from app.observation_graph import Observation, ObservationGraph


def _graph():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    return graph


def test_hypothesis_starts_unvalidated():
    hypotheses = build_hypotheses(_graph())

    assert len(hypotheses) == 1
    item = hypotheses[0]
    assert item.finding_id == "f1"
    assert item.status == "unvalidated"
    assert item.confidence == 0.35
    assert item.evidence_ids == ()


def test_hypothesis_becomes_partially_supported_after_independent_validation():
    graph = _graph()
    graph.add(
        Observation(
            "v1",
            "validation",
            "dry_run",
            "validator",
            parent_ids=("finding:f1",),
        )
    )

    item = build_hypotheses(graph)[0]

    assert item.status == "partially_supported"
    assert item.confidence == 0.35


def test_hypothesis_requires_observed_validation_and_evidence_for_support():
    graph = _graph()
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "validator",
            parent_ids=("finding:f1",),
        )
    )

    partial = build_hypotheses(graph)[0]
    assert partial.status == "partially_supported"
    assert partial.confidence == 0.75

    graph.add(
        Observation(
            "e1",
            "evidence",
            "artifact-1",
            "validator",
            parent_ids=("v1",),
            metadata={"artifact_kind": "validation"},
        )
    )

    supported = build_hypotheses(graph)[0]
    assert supported.status == "supported"
    assert supported.confidence == 0.95
    assert supported.evidence_ids == ("e1",)


def test_self_validation_never_supports_hypothesis():
    graph = _graph()
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "scanner",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "e1",
            "evidence",
            "artifact-1",
            "scanner",
            parent_ids=("v1",),
        )
    )

    item = build_hypotheses(graph)[0]

    assert item.status == "unvalidated"
    assert item.confidence == 0.35
    assert item.evidence_ids == ()


def test_hypothesis_snapshot_becomes_stale_when_graph_changes():
    graph = _graph()
    item = build_hypotheses(graph)[0]

    assert hypothesis_snapshot_is_current(item, graph) is True

    graph.add(
        Observation(
            "v-new",
            "validation",
            "observed",
            "validator",
            parent_ids=("finding:f1",),
        )
    )

    assert hypothesis_snapshot_is_current(item, graph) is False


def test_hypothesis_fingerprint_ignores_planner_decision_memory():
    graph = _graph()
    item = build_hypotheses(graph)[0]

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
            },
        )
    )

    assert hypothesis_snapshot_is_current(item, graph) is True


def test_hypothesis_fingerprint_ignores_unrelated_evidence():
    graph = _graph()
    item = build_hypotheses(graph)[0]

    graph.add(
        Observation(
            "e-unrelated",
            "evidence",
            "artifact-other",
            "report-engine",
            metadata={"artifact_kind": "report"},
        )
    )

    assert hypothesis_snapshot_is_current(item, graph) is True


def test_hypothesis_delta_explains_confidence_status_and_evidence_changes():
    previous = {
        "graph_fingerprint": "old",
        "hypotheses": [
            {
                "finding_id": "f1",
                "confidence": 0.35,
                "status": "unvalidated",
                "evidence_ids": [],
            }
        ],
    }
    current = {
        "graph_fingerprint": "new",
        "hypotheses": [
            {
                "finding_id": "f1",
                "confidence": 0.95,
                "status": "supported",
                "evidence_ids": ["e1"],
            }
        ],
    }

    delta = diff_hypothesis_snapshots(previous, current)

    assert delta["changed"] is True
    assert delta["from_fingerprint"] == "old"
    assert delta["to_fingerprint"] == "new"
    change = delta["changes"][0]
    assert change["confidence_delta"] == 0.6
    assert change["status_before"] == "unvalidated"
    assert change["status_after"] == "supported"
    assert change["evidence_added"] == ["e1"]
    assert change["evidence_removed"] == []


def test_hypothesis_delta_tracks_added_and_removed_findings():
    previous = {
        "graph_fingerprint": "old",
        "hypotheses": [{"finding_id": "removed", "confidence": 0.35}],
    }
    current = {
        "graph_fingerprint": "new",
        "hypotheses": [{"finding_id": "added", "confidence": 0.35}],
    }

    changes = {
        item["finding_id"]: item
        for item in diff_hypothesis_snapshots(previous, current)["changes"]
    }

    assert changes["added"]["change"] == "added"
    assert changes["removed"]["change"] == "removed"


def test_hypothesis_delta_is_empty_for_equivalent_snapshots():
    snapshot = {
        "graph_fingerprint": "same",
        "hypotheses": [
            {
                "finding_id": "f1",
                "confidence": 0.35,
                "status": "unvalidated",
                "evidence_ids": [],
            }
        ],
    }

    delta = diff_hypothesis_snapshots(snapshot, snapshot)

    assert delta["changed"] is False
    assert delta["changes"] == []


def test_stability_marks_single_snapshot_as_fresh():
    snapshots = [
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-11T10:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.35, "status": "unvalidated"}
            ],
        }
    ]

    item = summarize_hypothesis_stability(snapshots)[0]

    assert item["stability"] == "fresh"
    assert item["observed_snapshots"] == 1
    assert item["stable_streak"] == 1


def test_stability_marks_three_identical_snapshots_as_stable():
    snapshots = [
        {
            "graph_fingerprint": "c",
            "created_at": "2026-09-11T12:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.95, "status": "supported"}
            ],
        },
        {
            "graph_fingerprint": "b",
            "created_at": "2026-09-11T11:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.95, "status": "supported"}
            ],
        },
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-11T10:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.95, "status": "supported"}
            ],
        },
    ]

    item = summarize_hypothesis_stability(snapshots)[0]

    assert item["stability"] == "stable"
    assert item["stable_streak"] == 3
    assert item["stability_score"] > 0.5


def test_stability_detects_confidence_reversal_as_contradictory():
    snapshots = [
        {
            "graph_fingerprint": "c",
            "created_at": "2026-09-11T12:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.75, "status": "partially_supported"}
            ],
        },
        {
            "graph_fingerprint": "b",
            "created_at": "2026-09-11T11:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.95, "status": "supported"}
            ],
        },
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-11T10:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.35, "status": "unvalidated"}
            ],
        },
    ]

    item = summarize_hypothesis_stability(snapshots)[0]

    assert item["stability"] == "contradictory"
    assert item["confidence_reversals"] == 1
    assert item["status_transitions"] == 2
