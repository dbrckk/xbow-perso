from app.high_value_intelligence import build_high_value_intelligence
from app.observation_graph import ObservationGraph


def test_passive_endpoint_hint_can_raise_matching_public_case_focus():
    result = build_high_value_intelligence(
        ObservationGraph(),
        passive_response_intelligence={
            "source_map_hints": [],
            "endpoint_path_hints": ["/graphql"],
        },
    )
    graphql = next(
        item for item in result["focuses"]
        if item["family"] == "graphql-authorization"
    )
    assert graphql["score"] >= 50
    assert any("surface signals:" in reason for reason in graphql["reasons"])
    assert result["passive_response_signal_count"] == 1
    assert result["advisory_only"] is True
    assert result["automatic_exploitation"] is False


def test_passive_hints_do_not_create_execution_capability():
    result = build_high_value_intelligence(
        ObservationGraph(),
        passive_response_intelligence={
            "source_map_hints": ["https://example.test/app.js.map"],
            "endpoint_path_hints": ["/api/v1/profile"],
        },
    )
    assert result["scope_expansion"] is False
    assert result["automatic_exploitation"] is False
