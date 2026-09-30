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

    assert result["schema"] == "openapi-read-only-preview-v7"
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
    assert result["schema"] == "openapi-read-only-preview-v7"
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
    assert result["schema"] == "openapi-read-only-preview-v7"
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

    assert result["schema"] == "openapi-read-only-preview-v7"
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
    assert result["schema"] == "openapi-read-only-preview-v7"
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

    assert result["schema"] == "openapi-read-only-preview-v7"
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


def test_openapi_preview_preserves_parameter_name_at_maximum_length():
    parameter_name = "p" * 160
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "parameters": [
                            {
                                "name": parameter_name,
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

    assert result["cases"][0]["parameters"][0]["name"] == parameter_name
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_parameter_name_above_maximum_length():
    with pytest.raises(OpenApiPreviewError, match="160 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/items": {
                        "get": {
                            "parameters": [
                                {
                                    "name": "p" * 161,
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


def test_openapi_preview_preserves_response_content_type_at_maximum_length():
    media_type = "application/" + ("a" * 108)
    assert len(media_type) == 120

    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {media_type: {}},
                            }
                        }
                    }
                }
            },
        }
    )

    assert result["cases"][0]["response_content_types"] == [media_type]
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_response_content_type_above_maximum_length():
    media_type = "application/" + ("a" * 109)
    assert len(media_type) == 121

    with pytest.raises(OpenApiPreviewError, match="120 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/items": {
                        "get": {
                            "responses": {
                                "200": {
                                    "description": "ok",
                                    "content": {media_type: {}},
                                }
                            }
                        }
                    }
                },
            }
        )


def test_openapi_preview_preserves_response_code_at_maximum_length():
    response_code = "X" * 20
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "responses": {
                            response_code: {"description": "ok"}
                        }
                    }
                }
            },
        }
    )

    assert result["cases"][0]["response_codes"] == [response_code]
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_response_code_above_maximum_length():
    response_code = "X" * 21

    with pytest.raises(OpenApiPreviewError, match="20 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/items": {
                        "get": {
                            "responses": {
                                response_code: {"description": "ok"}
                            }
                        }
                    }
                },
            }
        )


def test_openapi_preview_preserves_parameter_schema_type_at_maximum_length():
    schema_type = "t" * 80
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "parameters": [
                            {
                                "name": "filter",
                                "in": "query",
                                "schema": {"type": schema_type},
                            }
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["cases"][0]["parameters"][0]["schema_type"] == schema_type
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_parameter_schema_type_above_maximum_length():
    schema_type = "t" * 81

    with pytest.raises(OpenApiPreviewError, match="80 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/items": {
                        "get": {
                            "parameters": [
                                {
                                    "name": "filter",
                                    "in": "query",
                                    "schema": {"type": schema_type},
                                }
                            ],
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        )


def test_openapi_preview_preserves_security_scheme_name_at_maximum_length():
    scheme_name = "s" * 160
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "components": {
                "securitySchemes": {
                    scheme_name: {"type": "http", "scheme": "bearer"}
                }
            },
            "security": [{scheme_name: []}],
            "paths": {
                "/items": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    auth = result["summary"]["authentication"]
    assert auth["security_schemes"][0]["name"] == scheme_name
    assert auth["referenced_scheme_names"] == [scheme_name]
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_security_scheme_name_above_maximum_length():
    scheme_name = "s" * 161

    with pytest.raises(OpenApiPreviewError, match="scheme name exceeds 160 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "components": {
                    "securitySchemes": {
                        scheme_name: {"type": "http", "scheme": "bearer"}
                    }
                },
                "paths": {
                    "/items": {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_openapi_preview_rejects_security_scheme_reference_above_maximum_length():
    scheme_name = "s" * 161

    with pytest.raises(OpenApiPreviewError, match="scheme reference exceeds 160 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "security": [{scheme_name: []}],
                "paths": {
                    "/items": {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_openapi_preview_preserves_auth_metadata_at_maximum_lengths():
    scheme_type = "t" * 80
    http_scheme = "h" * 80
    bearer_format = "b" * 80
    location = "i" * 40
    flow_name = "f" * 80

    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "components": {
                "securitySchemes": {
                    "auth": {
                        "type": scheme_type,
                        "scheme": http_scheme,
                        "bearerFormat": bearer_format,
                        "in": location,
                        "flows": {
                            flow_name: {
                                "authorizationUrl": "https://example.invalid/auth",
                                "tokenUrl": "https://example.invalid/token",
                                "scopes": {},
                            }
                        },
                    }
                }
            },
            "paths": {
                "/items": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    scheme = result["summary"]["authentication"]["security_schemes"][0]
    assert scheme["type"] == scheme_type
    assert scheme["scheme"] == http_scheme
    assert scheme["bearer_format"] == bearer_format
    assert scheme["in"] == location
    assert scheme["oauth_flows"] == [flow_name]
    assert result["network_requests_sent"] == 0


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("type", "t" * 81, "scheme type exceeds 80 characters"),
        ("scheme", "h" * 81, "HTTP auth scheme exceeds 80 characters"),
        ("bearerFormat", "b" * 81, "bearer format exceeds 80 characters"),
        ("in", "i" * 41, "scheme location exceeds 40 characters"),
    ],
)
def test_openapi_preview_rejects_overlong_auth_metadata(field, value, message):
    with pytest.raises(OpenApiPreviewError, match=message):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "components": {
                    "securitySchemes": {
                        "auth": {
                            "type": "http",
                            field: value,
                        }
                    }
                },
                "paths": {
                    "/items": {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_openapi_preview_rejects_overlong_oauth_flow_name():
    flow_name = "f" * 81

    with pytest.raises(OpenApiPreviewError, match="OAuth flow name exceeds 80 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "components": {
                    "securitySchemes": {
                        "oauth": {
                            "type": "oauth2",
                            "flows": {
                                flow_name: {
                                    "authorizationUrl": "https://example.invalid/auth",
                                    "tokenUrl": "https://example.invalid/token",
                                    "scopes": {},
                                }
                            },
                        }
                    }
                },
                "paths": {
                    "/items": {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_openapi_preview_preserves_tag_at_maximum_length():
    tag = "t" * 80
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "tags": [tag],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["cases"][0]["tags"] == [tag]
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_tag_above_maximum_length():
    with pytest.raises(OpenApiPreviewError, match="tag exceeds 80 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/items": {
                        "get": {
                            "tags": ["t" * 81],
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        )


def test_openapi_preview_preserves_source_version_at_maximum_length():
    version = "v" * 40
    result = build_openapi_read_only_preview(
        {
            "openapi": version,
            "paths": {
                "/health": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    assert result["source_version"] == version
    assert result["network_requests_sent"] == 0


def test_openapi_preview_rejects_source_version_above_maximum_length():
    with pytest.raises(OpenApiPreviewError, match="version exceeds 40 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "v" * 41,
                "paths": {
                    "/health": {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_swagger_preview_uses_document_produces_as_response_content_types():
    result = build_openapi_read_only_preview(
        {
            "swagger": "2.0",
            "produces": ["application/json", "text/plain"],
            "paths": {
                "/items": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    assert result["cases"][0]["response_content_types"] == [
        "application/json",
        "text/plain",
    ]
    assert result["network_requests_sent"] == 0


def test_swagger_preview_operation_produces_overrides_document_produces():
    result = build_openapi_read_only_preview(
        {
            "swagger": "2.0",
            "produces": ["application/json"],
            "paths": {
                "/items": {
                    "get": {
                        "produces": ["application/xml"],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["cases"][0]["response_content_types"] == ["application/xml"]
    assert result["network_requests_sent"] == 0


def test_swagger_preview_deduplicates_produces_metadata():
    result = build_openapi_read_only_preview(
        {
            "swagger": "2.0",
            "produces": ["application/json", "application/json"],
            "paths": {
                "/items": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    assert result["cases"][0]["response_content_types"] == ["application/json"]


def test_swagger_preview_rejects_overlong_produces_content_type():
    media_type = "application/" + ("a" * 109)
    assert len(media_type) == 121

    with pytest.raises(OpenApiPreviewError, match="120 characters"):
        build_openapi_read_only_preview(
            {
                "swagger": "2.0",
                "produces": [media_type],
                "paths": {
                    "/items": {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_swagger_preview_uses_document_consumes_as_request_content_types():
    result = build_openapi_read_only_preview(
        {
            "swagger": "2.0",
            "consumes": ["application/json", "application/x-www-form-urlencoded"],
            "paths": {
                "/items": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    assert result["schema"] == "openapi-read-only-preview-v7"
    assert result["cases"][0]["request_content_types"] == [
        "application/json",
        "application/x-www-form-urlencoded",
    ]
    assert result["network_requests_sent"] == 0


def test_swagger_preview_operation_consumes_overrides_document_consumes():
    result = build_openapi_read_only_preview(
        {
            "swagger": "2.0",
            "consumes": ["application/json"],
            "paths": {
                "/items": {
                    "get": {
                        "consumes": ["application/xml"],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["cases"][0]["request_content_types"] == ["application/xml"]
    assert result["network_requests_sent"] == 0


def test_swagger_preview_deduplicates_consumes_metadata():
    result = build_openapi_read_only_preview(
        {
            "swagger": "2.0",
            "consumes": ["application/json", "application/json"],
            "paths": {
                "/items": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
    )

    assert result["cases"][0]["request_content_types"] == ["application/json"]


def test_swagger_preview_rejects_overlong_consumes_content_type():
    media_type = "application/" + ("a" * 109)
    assert len(media_type) == 121

    with pytest.raises(OpenApiPreviewError, match="request content type exceeds 120 characters"):
        build_openapi_read_only_preview(
            {
                "swagger": "2.0",
                "consumes": [media_type],
                "paths": {
                    "/items": {
                        "get": {
                            "responses": {"200": {"description": "ok"}}
                        }
                    }
                },
            }
        )


def test_openapi3_preview_inventories_request_body_content_types():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "requestBody": {
                            "content": {
                                "application/json": {},
                                "application/problem+json": {},
                            }
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["schema"] == "openapi-read-only-preview-v7"
    assert result["cases"][0]["request_content_types"] == [
        "application/json",
        "application/problem+json",
    ]
    assert result["network_requests_sent"] == 0


def test_openapi3_preview_unions_request_body_content_with_consumes_metadata():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "consumes": ["application/json", "text/plain"],
            "paths": {
                "/items": {
                    "get": {
                        "requestBody": {
                            "content": {
                                "application/json": {},
                                "application/xml": {},
                            }
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["cases"][0]["request_content_types"] == [
        "application/json",
        "application/xml",
        "text/plain",
    ]


def test_openapi3_preview_skips_referenced_request_body_metadata():
    result = build_openapi_read_only_preview(
        {
            "openapi": "3.1.0",
            "paths": {
                "/items": {
                    "get": {
                        "requestBody": {
                            "$ref": "https://example.invalid/request-body.json"
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
    )

    assert result["cases"][0]["request_content_types"] == []
    assert result["network_requests_sent"] == 0


def test_openapi3_preview_rejects_overlong_request_content_type():
    media_type = "application/" + ("a" * 109)
    assert len(media_type) == 121

    with pytest.raises(OpenApiPreviewError, match="request content type exceeds 120 characters"):
        build_openapi_read_only_preview(
            {
                "openapi": "3.1.0",
                "paths": {
                    "/items": {
                        "get": {
                            "requestBody": {
                                "content": {media_type: {}}
                            },
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        )
