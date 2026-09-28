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

    assert result["schema"] == "openapi-read-only-preview-v6"
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
    assert result["schema"] == "openapi-read-only-preview-v6"
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
    assert result["schema"] == "openapi-read-only-preview-v6"
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


def test_openapi_preview_prioritizes_review_without_execution_effect():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "security": [{"oauth2": ["read"]}],
            "paths": {
                "/health": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                },
                "/users/{user_id}/callback": {
                    "get": {
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
                },
            },
        }
    )

    assert result["schema"] == "openapi-read-only-preview-v6"
    assert result["network_requests_sent"] == 0
    assert result["execution_mode"] == "preview_only"
    assert result["cases"][0]["path"] == "/users/{user_id}/callback"
    assert 0 < result["cases"][0]["review_priority"] <= 100
    assert "bola_idor_review" in result["cases"][0]["review_priority_reasons"]
    assert "ssrf_input_review" in result["cases"][0]["review_priority_reasons"]
    assert "authenticated_surface" in result["cases"][0]["review_priority_reasons"]
    assert result["cases"][1]["path"] == "/health"
    assert result["cases"][1]["review_priority"] > 0
    assert all(
        signal["vulnerability_confirmed"] is False
        for case in result["cases"]
        for signal in case["risk_signals"]
    )


def test_openapi_preview_zero_priority_without_risk_signals():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/health": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    case = result["cases"][0]
    assert case["review_priority"] == 0
    assert case["review_priority_reasons"] == []
    assert case["risk_signals"] == []
    assert result["network_requests_sent"] == 0


def test_openapi_preview_exposes_advisory_review_summary():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "security": [{"oauth2": ["read"]}],
            "paths": {
                "/health": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                },
                "/users/{user_id}/callback": {
                    "get": {
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
                },
            },
        }
    )

    review = result["summary"]["review"]
    assert result["schema"] == "openapi-read-only-preview-v6"
    assert result["network_requests_sent"] == 0
    assert review["advisory"] is True
    assert review["vulnerabilities_confirmed"] == 0
    assert review["flagged_operations"] == 2
    assert review["unflagged_operations"] == 0
    assert review["max_review_priority"] == result["cases"][0]["review_priority"]
    assert review["category_counts"]["bola_idor_review"] == 1
    assert review["category_counts"]["ssrf_input_review"] == 1
    assert review["category_counts"]["sensitive_data_review"] == 1
    assert review["category_counts"]["auth_session_review"] == 2
    assert review["top_review_operations"][0]["path"] == "/users/{user_id}/callback"


def test_openapi_review_summary_is_empty_for_unflagged_spec():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/health": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    review = result["summary"]["review"]
    assert review == {
        "advisory": True,
        "vulnerabilities_confirmed": 0,
        "flagged_operations": 0,
        "unflagged_operations": 1,
        "max_review_priority": 0,
        "category_counts": {},
        "top_review_operations": [],
    }


def test_openapi_preview_inventories_openapi3_authentication_metadata():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT",
                    },
                    "oauth2": {
                        "type": "oauth2",
                        "flows": {
                            "authorizationCode": {
                                "authorizationUrl": "https://auth.example.invalid/authorize",
                                "tokenUrl": "https://auth.example.invalid/token",
                                "scopes": {"read": "Read access"},
                            }
                        },
                    },
                    "oidc": {
                        "type": "openIdConnect",
                        "openIdConnectUrl": "https://auth.example.invalid/.well-known/openid-configuration",
                    },
                }
            },
            "security": [{"bearerAuth": []}],
            "paths": {
                "/account": {
                    "get": {
                        "security": [{"oauth2": ["read"]}],
                        "responses": {"200": {"description": "ok"}},
                    }
                },
                "/public": {
                    "get": {
                        "security": [],
                        "responses": {"200": {"description": "ok"}},
                    }
                },
            },
        }
    )

    assert result["schema"] == "openapi-read-only-preview-v6"
    auth = result["summary"]["authentication"]
    assert auth["advisory"] is True
    assert auth["vulnerabilities_confirmed"] == 0
    assert auth["defined_scheme_count"] == 3
    assert auth["referenced_scheme_names"] == ["oauth2"]
    assert auth["unknown_scheme_references"] == []
    assert auth["explicit_public_overrides"] == [{"method": "GET", "path": "/public"}]

    schemes = {item["name"]: item for item in auth["security_schemes"]}
    assert schemes["bearerAuth"]["type"] == "http"
    assert schemes["bearerAuth"]["scheme"] == "bearer"
    assert schemes["bearerAuth"]["bearer_format"] == "JWT"
    assert schemes["oauth2"]["oauth_flows"] == ["authorizationCode"]
    assert schemes["oidc"]["open_id_connect"] is True
    rendered = str(auth)
    assert "authorizationUrl" not in rendered
    assert "tokenUrl" not in rendered
    assert ".well-known" not in rendered
    assert result["network_requests_sent"] == 0


def test_openapi_preview_flags_unknown_auth_scheme_reference_advisory_only():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "components": {
                "securitySchemes": {
                    "known": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
                }
            },
            "paths": {
                "/reports": {
                    "get": {
                        "security": [{"missingScheme": []}],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    case = result["cases"][0]
    auth = result["summary"]["authentication"]
    assert case["security_scheme_names"] == ["missingScheme"]
    assert case["security_source"] == "operation"
    assert case["explicitly_public"] is False
    assert auth["unknown_scheme_references"] == ["missingScheme"]
    assert auth["vulnerabilities_confirmed"] == 0
    assert result["network_requests_sent"] == 0


def test_swagger2_auth_inventory_is_metadata_only():
    result = build_openapi_read_only_preview(
        {
            "swagger": "2.0",
            "securityDefinitions": {
                "legacyOauth": {
                    "type": "oauth2",
                    "flow": "accessCode",
                    "authorizationUrl": "https://auth.example.invalid/authorize",
                    "tokenUrl": "https://auth.example.invalid/token",
                    "scopes": {"read": "Read"},
                },
                "apiKey": {
                    "type": "apiKey",
                    "name": "X-API-Key",
                    "in": "header",
                },
            },
            "security": [{"legacyOauth": ["read"]}],
            "paths": {
                "/items": {
                    "get": {"responses": {"200": {"description": "ok"}}}
                }
            },
        }
    )

    auth = result["summary"]["authentication"]
    assert auth["defined_scheme_count"] == 2
    schemes = {item["name"]: item for item in auth["security_schemes"]}
    assert schemes["legacyOauth"]["oauth_flows"] == ["accessCode"]
    assert schemes["apiKey"]["type"] == "apikey"
    assert schemes["apiKey"]["in"] == "header"
    assert auth["referenced_scheme_names"] == ["legacyOauth"]
    assert result["cases"][0]["security_source"] == "document"
    assert result["network_requests_sent"] == 0


def test_openapi_risk_matching_avoids_id_substring_false_positives():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/public/directory": {
                    "get": {
                        "operationId": "listDirectoryProviders",
                        "parameters": [
                            {
                                "name": "provider",
                                "in": "query",
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    categories = {
        item["category"]
        for item in result["cases"][0]["risk_signals"]
    }
    assert "bola_idor_review" not in categories
    assert result["network_requests_sent"] == 0


def test_openapi_risk_matching_keeps_structured_object_identifier_signal():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/users/{user_id}": {
                    "get": {
                        "parameters": [
                            {
                                "name": "user_id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    signals = result["cases"][0]["risk_signals"]
    bola = next(item for item in signals if item["category"] == "bola_idor_review")
    assert "user_id" in bola["evidence"]
    assert result["network_requests_sent"] == 0


def test_openapi_risk_matching_keeps_compound_ssrf_input_signal():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/callbacks": {
                    "get": {
                        "parameters": [
                            {
                                "name": "callback_url",
                                "in": "query",
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    signals = result["cases"][0]["risk_signals"]
    ssrf = next(item for item in signals if item["category"] == "ssrf_input_review")
    assert "callback_url" in ssrf["evidence"]
    assert result["network_requests_sent"] == 0


def test_openapi_string_tags_are_ignored_instead_of_iterated():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/health": {
                    "get": {
                        "tags": "user_id",
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    case = result["cases"][0]
    assert case["tags"] == []
    assert case["risk_signals"] == []
    assert case["review_priority"] == 0
    assert result["network_requests_sent"] == 0


def test_openapi_preview_preserves_path_at_maximum_length():
    path = "/" + ("a" * 2047)
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                path: {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    assert len(path) == 2048
    assert result["cases"][0]["path"] == path
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_path_above_maximum_length():
    path = "/" + ("a" * 2048)

    with pytest.raises(OpenApiPreviewError, match="2048 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "paths": {
                    path: {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_openapi_preview_rejects_document_above_two_mib():
    oversized = "x" * (2 * 1024 * 1024)
    with pytest.raises(OpenApiPreviewError, match="2097152 bytes"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "info": {"description": oversized},
                "paths": {
                    "/health": {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_openapi_preview_accepts_normal_document_under_size_bound():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "info": {"description": "bounded passive preview"},
            "paths": {
                "/health": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    assert result["cases"][0]["path"] == "/health"
    assert result["network_requests_sent"] == 0


def test_openapi_preview_api_maps_oversized_document_to_bad_request():
    oversized = "x" * (2 * 1024 * 1024)

    with pytest.raises(main.HTTPException) as exc:
        main.preview_openapi_tests(
            main.OpenApiPreviewInput(
                document={
                    "openapi": "3.1.0",
                    "info": {"description": oversized},
                    "paths": {
                        "/health": {
                            "get": {
                                "responses": {"200": {"description": "ok"}}
                            }
                        }
                    },
                }
            )
        )

    assert exc.value.status_code == 400
    assert "2097152 bytes" in str(exc.value.detail)


def test_openapi_preview_normalizes_blank_operation_id_to_none():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/health": {
                    "get": {
                        "operationId": "   ",
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["cases"][0]["operation_id"] is None
    assert result["network_requests_sent"] == 0


def test_openapi_preview_preserves_operation_id_at_maximum_length():
    operation_id = "a" * 160
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/health": {
                    "get": {
                        "operationId": operation_id,
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["cases"][0]["operation_id"] == operation_id
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_operation_id_above_maximum_length():
    with pytest.raises(OpenApiPreviewError, match="160 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/health": {
                        "get": {
                            "operationId": "a" * 161,
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        )
