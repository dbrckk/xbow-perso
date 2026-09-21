import json

from app.passive_api_intelligence import analyze_api_schema_text


def test_extracts_graphql_operation_names_without_generating_requests():
    result = analyze_api_schema_text(
        "query Viewer { viewer { id name } } mutation Rename { renameUser { id } }"
    )
    assert {"type": "query", "name": "Viewer"} in result["graphql_operation_names"]
    assert {"type": "mutation", "name": "Rename"} in result["graphql_operation_names"]
    assert result["network_requests_performed"] == 0
    assert result["request_payloads_generated"] == 0


def test_extracts_openapi_paths_and_methods_from_existing_document():
    body = json.dumps({
        "openapi": "3.0.0",
        "paths": {
            "/api/v1/profile": {"get": {}, "patch": {}},
            "/api/v1/items/{id}": {"get": {}, "delete": {}},
        },
    })
    result = analyze_api_schema_text(body, content_type="application/json")
    assert "/api/v1/profile" in result["openapi_paths"]
    assert result["openapi_methods"]["/api/v1/profile"] == ["GET", "PATCH"]
    assert result["automatic_execution"] is False
    assert result["scope_expansion"] is False


def test_invalid_json_remains_fail_closed():
    result = analyze_api_schema_text("{not-json")
    assert result["openapi_paths"] == []
    assert result["request_payloads_generated"] == 0
