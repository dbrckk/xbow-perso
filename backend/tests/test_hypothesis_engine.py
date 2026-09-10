from app.hypothesis_engine import build_hypotheses
from app.observation_graph import Observation, ObservationGraph


def test_hypotheses_are_bounded_and_deterministic():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://example.test/account?id=1",
            "recon",
            parent_ids=("a1",),
        )
    )
    graph.add(Observation("t1", "technology", "framework-x", "recon", parent_ids=("a1",)))

    first = build_hypotheses(graph, limit=2)
    second = build_hypotheses(graph, limit=2)

    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert len(first) == 2
    assert first[0].kind == "authorization_surface_review"
    assert all(item.next_action in {"scan", "validate", "stop"} for item in first)


def test_unvalidated_finding_gets_high_priority_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))

    hypotheses = build_hypotheses(graph)

    assert hypotheses[0].kind == "validation_gap"
    assert hypotheses[0].confidence == 0.90
    assert hypotheses[0].next_action == "validate"


def test_observed_independent_validation_closes_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )

    assert build_hypotheses(graph) == []


def test_self_validation_does_not_close_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "scanner",
            parent_ids=("finding:f1",),
        )
    )

    hypotheses = build_hypotheses(graph)
    assert hypotheses[0].kind == "validation_gap"


def test_limit_fails_closed_outside_bounds():
    graph = ObservationGraph()

    for invalid in (0, 101):
        try:
            build_hypotheses(graph, limit=invalid)
        except ValueError as exc:
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("invalid limit should fail")
