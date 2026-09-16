from app.differential_intelligence import (
    build_differential_signals,
    classify_differential_signal,
)
from app.observation_graph import Observation, ObservationGraph


def test_differential_signal_classification_is_conservative():
    assert classify_differential_signal(None) == "none"
    assert classify_differential_signal({"eligible": False}) == "none"
    assert classify_differential_signal({"eligible": True, "reason": "marker_request_error"}) == "none"
    assert classify_differential_signal(
        {
            "eligible": True,
            "marker_reflected": False,
            "status_changed": False,
            "body_changed": False,
        }
    ) == "none"
    assert classify_differential_signal(
        {
            "eligible": True,
            "marker_reflected": False,
            "status_changed": False,
            "body_changed": True,
        }
    ) == "weak"
    assert classify_differential_signal(
        {
            "eligible": True,
            "marker_reflected": False,
            "status_changed": True,
            "body_changed": False,
        }
    ) == "weak"
    assert classify_differential_signal(
        {
            "eligible": True,
            "marker_reflected": True,
            "status_changed": False,
            "body_changed": True,
        }
    ) == "strong"


def test_graph_signal_aggregation_prefers_strong_and_preserves_provenance():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "validation:weak",
            "validation",
            "observed",
            "independent-http-validator",
            parent_ids=("finding:f1",),
            metadata={
                "finding_id": "f1",
                "differential_signal": "weak",
                "differential_parameter": "q",
                "differential_marker_reflected": False,
                "differential_status_changed": False,
                "differential_body_changed": True,
            },
        )
    )
    graph.add(
        Observation(
            "validation:strong",
            "validation",
            "observed",
            "independent-http-validator",
            parent_ids=("finding:f1",),
            metadata={
                "finding_id": "f1",
                "differential_signal": "strong",
                "differential_parameter": "q",
                "differential_marker_reflected": True,
                "differential_status_changed": False,
                "differential_body_changed": True,
                "differential_baseline_status": 200,
                "differential_marker_status": 200,
            },
        )
    )

    signals = build_differential_signals(graph)
    signal = signals["f1"]

    assert signal.signal == "strong"
    assert signal.parameter == "q"
    assert signal.marker_reflected is True
    assert signal.status_changed is False
    assert signal.body_changed is True
    assert signal.baseline_status == 200
    assert signal.marker_status == 200
    assert signal.observation_ids == ("validation:strong", "validation:weak")
    assert signal.to_dict()["observation_ids"] == ["validation:strong", "validation:weak"]


def test_graph_signal_aggregation_defaults_to_none_for_findings_without_differential_metadata():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("asset:a",),
        )
    )

    signals = build_differential_signals(graph)

    assert signals["f1"].signal == "none"
    assert signals["f1"].observation_ids == ()
