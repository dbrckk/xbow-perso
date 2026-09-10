from app.observation_graph import Observation, ObservationGraph
from app.validation_state import (
    attempted_finding_ids,
    has_observed_independent_validation,
    observed_independent_finding_ids,
)


def _graph(validation_value="observed", validation_source="validator"):
    graph = ObservationGraph()
    graph.add(Observation(id="finding:f1", kind="finding", value="candidate", source="scanner"))
    graph.add(
        Observation(
            id="validation:v1",
            kind="validation",
            value=validation_value,
            source=validation_source,
            parent_ids=("finding:f1",),
        )
    )
    return graph


def test_observed_independent_validation_is_recognized():
    graph = _graph()
    assert observed_independent_finding_ids(graph) == {"finding:f1"}
    assert has_observed_independent_validation(graph, "finding:f1") is True


def test_self_validation_does_not_count_as_independent():
    graph = _graph(validation_source="scanner")
    assert observed_independent_finding_ids(graph) == set()
    assert has_observed_independent_validation(graph, "finding:f1") is False


def test_non_observed_attempt_counts_only_as_attempt():
    graph = _graph(validation_value="dry_run")
    assert attempted_finding_ids(graph) == {"finding:f1"}
    assert observed_independent_finding_ids(graph) == set()


def test_mixed_validation_states_remain_finding_specific():
    graph = ObservationGraph()
    graph.add(Observation(id="finding:f1", kind="finding", value="candidate", source="scanner-a"))
    graph.add(Observation(id="finding:f2", kind="finding", value="candidate", source="scanner-b"))
    graph.add(
        Observation(
            id="validation:v1",
            kind="validation",
            value="observed",
            source="validator-a",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            id="validation:v2",
            kind="validation",
            value="error",
            source="validator-b",
            parent_ids=("finding:f2",),
        )
    )

    assert attempted_finding_ids(graph) == {"finding:f1", "finding:f2"}
    assert observed_independent_finding_ids(graph) == {"finding:f1"}
    assert has_observed_independent_validation(graph, "finding:f1") is True
    assert has_observed_independent_validation(graph, "finding:f2") is False


def test_validation_ignores_non_finding_parent_ids():
    graph = ObservationGraph()
    graph.add(Observation(id="endpoint:e1", kind="endpoint", value="https://example.test/", source="recon"))
    graph.add(Observation(id="finding:f1", kind="finding", value="candidate", source="scanner"))
    graph.add(
        Observation(
            id="validation:v1",
            kind="validation",
            value="observed",
            source="validator",
            parent_ids=("endpoint:e1", "finding:f1"),
        )
    )

    assert attempted_finding_ids(graph) == {"finding:f1"}
    assert observed_independent_finding_ids(graph) == {"finding:f1"}
    assert has_observed_independent_validation(graph, "endpoint:e1") is False
