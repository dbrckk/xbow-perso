from app.observation_graph import Observation, ObservationGraph
from app.validation_state import (
    analyze_validation_state,
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
    state = analyze_validation_state(graph)
    assert attempted_finding_ids(graph) == {"finding:f1"}
    assert observed_independent_finding_ids(graph) == set()
    assert state.unresolved_finding_ids == {"finding:f1"}
    assert state.unattempted_finding_ids == frozenset()
    assert state.all_observed_independently is False


def test_unattempted_finding_is_exposed_explicitly():
    graph = ObservationGraph()
    graph.add(Observation(id="finding:f1", kind="finding", value="candidate", source="scanner"))

    state = analyze_validation_state(graph)

    assert state.finding_ids == {"finding:f1"}
    assert state.attempted_finding_ids == frozenset()
    assert state.unresolved_finding_ids == {"finding:f1"}
    assert state.unattempted_finding_ids == {"finding:f1"}
    assert state.all_observed_independently is False


def test_empty_graph_is_not_treated_as_fully_validated():
    state = analyze_validation_state(ObservationGraph())
    assert state.finding_ids == frozenset()
    assert state.all_observed_independently is False


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

    state = analyze_validation_state(graph)
    assert attempted_finding_ids(graph) == {"finding:f1", "finding:f2"}
    assert observed_independent_finding_ids(graph) == {"finding:f1"}
    assert state.unresolved_finding_ids == {"finding:f2"}
    assert state.unattempted_finding_ids == frozenset()
    assert has_observed_independent_validation(graph, "finding:f1") is True
    assert has_observed_independent_validation(graph, "finding:f2") is False


def test_multiple_attempts_can_upgrade_to_observed_independent_state():
    graph = ObservationGraph()
    graph.add(Observation(id="finding:f1", kind="finding", value="candidate", source="scanner"))
    graph.add(
        Observation(
            id="validation:dry",
            kind="validation",
            value="dry_run",
            source="validator-a",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            id="validation:observed",
            kind="validation",
            value="observed",
            source="validator-b",
            parent_ids=("finding:f1",),
        )
    )

    state = analyze_validation_state(graph)
    assert state.attempted_finding_ids == {"finding:f1"}
    assert state.observed_independent_finding_ids == {"finding:f1"}
    assert state.unresolved_finding_ids == frozenset()
    assert state.all_observed_independently is True


def test_non_finding_validation_parent_is_ignored():
    graph = ObservationGraph()
    graph.add(Observation(id="endpoint:e1", kind="endpoint", value="https://example.test", source="recon"))
    graph.add(
        Observation(
            id="validation:v1",
            kind="validation",
            value="observed",
            source="validator",
            parent_ids=("endpoint:e1",),
        )
    )

    state = analyze_validation_state(graph)
    assert state.finding_ids == frozenset()
    assert state.attempted_finding_ids == frozenset()
    assert state.observed_independent_finding_ids == frozenset()
