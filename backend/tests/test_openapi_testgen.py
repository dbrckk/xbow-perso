import pytest

from app import main
from app.openapi_testgen import OpenApiPreviewError, build_openapi_read_only_preview
from app.offensive_expansion import offensive_expansion_catalog


def test_openapi_preview_generates_only_read_only_cases():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "security": [{"bearerAuth": []}],
            "paths": {
                "/users": {
                    "get": {"operationId": "listUsers", "tags": ["users"]},
                    "post": {"operationId": "createUser"},
                },
                "/health": {
                    "head": {"operationId": "headHealth", "security": []},
                    "delete": {"operationId": "deleteHealth"},
                },
            },
        }
    )

    assert result["execution_mode"] == "preview_only"
    assert result["read_only"] is True
    assert result["network_requests_sent"] == 0
    assert {case["method"] for case in result["cases"]} == {"GET", "HEAD"}
    assert all(case["read_only"] is True for case in result["cases"])
    assert all(case["destructive"] is False for case in result["cases"])
    assert result["summary"]["mutating_operations_skipped"] == 2
    by_method = {case["method"]: case for case in result["cases"]}
    assert by_method["GET"]["authentication_declared"] is True
    assert by_method["HEAD"]["authentication_declared"] is False


def test_openapi_preview_rejects_missing_version():
    with pytest.raises(OpenApiPreviewError, match="version"):
        build_openapi_read_only_preview({"paths": {}})


def test_openapi_preview_rejects_excessive_paths():
    paths = {f"/p{index}": {"get": {}} for index in range(251)}
    with pytest.raises(OpenApiPreviewError, match="250 paths"):
        build_openapi_read_only_preview({"openapi": "3.1.0", "paths": paths})


def test_openapi_preview_api_is_read_only_and_bounded():
    result = main.preview_openapi_tests(
        main.OpenApiPreviewInput(
            document={
                "swagger": "2.0",
                "paths": {
                    "/items": {
                        "get": {"operationId": "getItems"},
                        "patch": {"operationId": "patchItems"},
                    }
                },
            }
        )
    )

    assert result["schema"] == "openapi-read-only-preview-v3"
    assert [item["method"] for item in result["cases"]] == ["GET"]
    assert result["summary"]["mutating_operations_skipped"] == 1


def test_expansion_catalog_keeps_active_authority_unchanged():
    catalog = offensive_expansion_catalog()
    by_id = {item["id"]: item for item in catalog["capabilities"]}

    assert catalog["execution_authority"] == "unchanged"
    assert by_id["api.openapi_test_generation"]["mode"] == "read_only_preview"
    assert by_id["fuzz.ffuf"]["mode"] == "preview_only"
    assert by_id["fuzz.wfuzz"]["mode"] == "preview_only"
    assert by_id["validation.sqlmap"]["mode"] == "preview_only"
    assert by_id["validation.metasploit"]["mode"] == "preview_only"
    assert by_id["reasoning.ai_prioritization"]["status"] == "integrated"
    assert by_id["correlation.knowledge_graph"]["status"] == "integrated"
    assert by_id["orchestration.workflows"]["status"] == "integrated"


def test_expansion_routes_are_present_in_openapi():
    paths = main.app.openapi()["paths"]
    assert "/api/testing/openapi/preview" in paths
    assert "/api/testing/offensive-expansion" in paths


def test_openapi_preview_extracts_passive_parameter_and_response_metadata():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/users/{user_id}": {
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "get": {
                        "parameters": [
                            {
                                "name": "include",
                                "in": "query",
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "X-Trace",
                                "in": "header",
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {
                                    "application/json": {},
                                    "application/problem+json": {},
                                },
                            },
                            "404": {"description": "not found"},
                        },
                    },
                }
            },
        }
    )

    case = result["cases"][0]
    assert result["schema"] == "openapi-read-only-preview-v2"
    assert case["method"] == "GET"
    assert case["parameters"] == [
        {
            "name": "user_id",
            "in": "path",
            "required": True,
            "schema_type": "string",
        },
        {
            "name": "include",
            "in": "query",
            "required": False,
            "schema_type": "string",
        },
        {
            "name": "X-Trace",
            "in": "header",
            "required": False,
            "schema_type": "string",
        },
    ]
    assert case["response_codes"] == ["200", "404"]
    assert case["response_content_types"] == [
        "application/json",
        "application/problem+json",
    ]
    assert result["network_requests_sent"] == 0


def test_openapi_preview_ignores_external_parameter_refs():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "parameters": [
                            {"$ref": "https://example.invalid/parameters.json#/Limit"}
                        ]
                    }
                }
            },
        }
    )

    assert result["cases"][0]["parameters"] == []


def test_openapi_preview_emits_advisory_api_risk_signals_only():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "security": [{"oauth2": ["read"]}],
            "paths": {
                "/users/{user_id}/callback": {
                    "get": {
                        "operationId": "getUserCallback",
                        "parameters": [
                            {
                                "name": "user_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "callback_url",
                                "in": "query",
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "email",
                                "in": "query",
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    case = result["cases"][0]
    categories = {item["category"] for item in case["risk_signals"]}
    assert result["schema"] == "openapi-read-only-preview-v3"
    assert "bola_idor_review" in categories
    assert "ssrf_input_review" in categories
    assert "auth_session_review" in categories
    assert "sensitive_data_review" in categories
    assert all(item["advisory"] is True for item in case["risk_signals"])
    assert all(item["vulnerability_confirmed"] is False for item in case["risk_signals"])
    assert result["network_requests_sent"] == 0


def test_openapi_preview_does_not_claim_vulnerability_from_path_name_only():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/public/url-directory": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    signals = result["cases"][0]["risk_signals"]
    assert signals
    assert all(item["vulnerability_confirmed"] is False for item in signals)
