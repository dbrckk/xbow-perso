from app.observation_graph import Observation, ObservationGraph
from app.passive_response_context import build_passive_response_context


def test_context_uses_only_existing_in_scope_response_bodies():
    graph = ObservationGraph()
    graph.add(Observation(
        id="one",
        kind="endpoint",
        value="https://example.test/app.js",
        source="browser",
        metadata={
            "url": "https://example.test/app.js",
            "content_type": "application/javascript",
            "response_body": 'fetch("/api/v1/me");\n//# sourceMappingURL=app.js.map',
        },
    ))
    graph.add(Observation(
        id="two",
        kind="endpoint",
        value="https://outside.test/app.js",
        source="browser",
        metadata={
            "url": "https://outside.test/app.js",
            "response_body": 'fetch("/api/private")',
        },
    ))

    result = build_passive_response_context(
        graph,
        scope_checker=lambda host: host == "example.test",
    )
    assert result["responses_analyzed"] == 1
    assert result["source_map_hints"] == ["https://example.test/app.js.map"]
    assert "/api/v1/me" in result["endpoint_path_hints"]
    assert "/api/private" not in result["endpoint_path_hints"]
    assert result["network_requests_performed"] == 0
    assert result["automatic_execution"] is False
    assert result["scope_expansion"] is False
