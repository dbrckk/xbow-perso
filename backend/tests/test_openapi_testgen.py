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
    assert result["cases"][0]["authentication_declared"] is True
    assert result["cases"][1]["authentication_declared"] is False


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

    assert result["schema"] == "openapi-read-only-preview-v1"
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
