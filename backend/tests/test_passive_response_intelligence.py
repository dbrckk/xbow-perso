from app.passive_response_intelligence import analyze_public_text_response


def test_extracts_same_origin_source_map_and_endpoint_hints():
    result = analyze_public_text_response(
        url="https://example.test/assets/app.js",
        content_type="application/javascript",
        body='fetch("/api/v1/profile");\n//# sourceMappingURL=app.js.map',
    )
    assert result["source_map_hints"] == ["https://example.test/assets/app.js.map"]
    assert "/api/v1/profile" in result["endpoint_path_hints"]
    assert result["network_requests_performed"] == 0


def test_does_not_return_potential_secret_values():
    result = analyze_public_text_response(
        url="https://example.test/app.js",
        body='api_key = "do-not-retain-this-value"',
    )
    assert result["potential_secret_shape_count"] == 1
    assert result["potential_secret_values_retained"] is False
    assert "do-not-retain-this-value" not in repr(result)


def test_cross_origin_source_map_hint_is_not_promoted():
    result = analyze_public_text_response(
        url="https://example.test/app.js",
        body="//# sourceMappingURL=https://other.test/app.js.map",
    )
    assert result["source_map_hints"] == []
    assert result["automatic_execution"] is False
    assert result["scope_expansion"] is False
