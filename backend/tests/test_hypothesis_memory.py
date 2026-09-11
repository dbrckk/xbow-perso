from app.hypothesis_memory import build_hypotheses
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
