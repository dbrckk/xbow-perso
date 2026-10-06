from app.differential_quality import (
    DIFFERENTIAL_QUALITY_SCHEMA,
    build_differential_quality,
)
from app.observation_graph import Observation, ObservationGraph


def _graph() -> ObservationGraph:
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner-a",
            parent_ids=("asset:a",),
        )
    )
    return graph


def _add_validation(
    graph: ObservationGraph,
    observation_id: str,
    *,
    source: str = "validator-a",
    signal: str = "strong",
    parameter: str = "q",
    reflected: bool = True,
    status_changed: bool = False,
    body_changed: bool = True,
) -> None:
    graph.add(
        Observation(
            observation_id,
            "validation",
            "observed",
            source,
            parent_ids=("finding:f1",),
            metadata={
                "finding_id": "f1",
                "differential_signal": signal,
                "differential_parameter": parameter,
                "differential_marker_reflected": reflected,
                "differential_status_changed": status_changed,
                "differential_body_changed": body_changed,
            },
        )
    )


def test_quality_defaults_to_high_false_positive_risk_without_observations():
    result = build_differential_quality(_graph())["f1"]

    assert result.schema == DIFFERENTIAL_QUALITY_SCHEMA
    assert result.observation_count == 0
    assert result.reproducible is False
    assert result.quality_score == 0.0
    assert result.false_positive_risk == "high"
    assert result.exploitability_confirmed is False
    assert result.zero_day_claim is False


def test_single_marker_reflection_is_specific_but_not_reproducible():
    graph = _graph()
    _add_validation(graph, "validation:one")

    result = build_differential_quality(graph)["f1"]

    assert result.strong_observation_count == 1
    assert result.marker_reflection_count == 1
    assert result.specificity_level == "high"
    assert result.reproducibility_level == "single"
    assert result.reproducible is False
    assert result.false_positive_risk == "medium"


def test_repeated_same_parameter_signal_reduces_false_positive_risk():
    graph = _graph()
    _add_validation(graph, "validation:one")
    _add_validation(graph, "validation:two")

    result = build_differential_quality(graph)["f1"]

    assert result.strong_observation_count == 2
    assert result.strong_parameters == ("q",)
    assert result.strong_parameter_consistent is True
    assert result.reproducible is True
    assert result.reproducibility_level == "repeated"
    assert result.quality_score >= 0.8
    assert result.false_positive_risk == "low"


def test_multi_validator_repeat_is_highest_reproducibility_level():
    graph = _graph()
    _add_validation(graph, "validation:one", source="validator-a")
    _add_validation(graph, "validation:two", source="validator-b")

    result = build_differential_quality(graph)["f1"]

    assert result.validator_source_count == 2
    assert result.reproducibility_level == "multi_source_repeated"
    assert result.reproducible is True
    assert result.quality_score >= 0.9


def test_mixed_signal_on_same_parameter_is_flagged_as_contradictory():
    graph = _graph()
    _add_validation(graph, "validation:strong", source="validator-a")
    _add_validation(
        graph,
        "validation:weak",
        source="validator-b",
        signal="weak",
        reflected=False,
        status_changed=False,
        body_changed=True,
    )

    result = build_differential_quality(graph)["f1"]

    assert result.contradictory is True
    assert result.reproducible is False
    assert result.false_positive_risk == "high"
    assert result.exploitability_confirmed is False


def test_quality_does_not_persist_parameter_values():
    graph = _graph()
    _add_validation(graph, "validation:one", parameter="token")

    serialized = str(build_differential_quality(graph)["f1"].to_dict())

    assert "private-value" not in serialized
    assert "token" in serialized
