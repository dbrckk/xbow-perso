import pytest
from fastapi import HTTPException

from app.main import (
    HackerOneScopePreviewInput,
    app,
    preview_hackerone_scope,
)


def _resource(identifier: str, asset_type: str, eligible: bool):
    return {
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": asset_type,
            "eligible_for_submission": eligible,
        },
    }


def test_hackerone_scope_preview_api_is_non_persisting():
    result = preview_hackerone_scope(
        HackerOneScopePreviewInput(
            document={
                "data": [
                    _resource("example.com", "Domain", True),
                    _resource("blocked.example.com", "Domain", False),
                ],
                "links": {},
            }
        )
    )

    assert result["provider"] == "hackerone"
    assert result["complete"] is True
    assert result["requires_review"] is True
    assert result["persisted"] is False
    assert result["campaign_created"] is False
    assert result["allowed_targets"] == ["example.com"]
    assert result["denied_targets"] == ["blocked.example.com"]
    assert len(result["assets"]) == 2


def test_hackerone_scope_preview_api_surfaces_unsupported_without_converting():
    result = preview_hackerone_scope(
        HackerOneScopePreviewInput(
            document={
                "data": [
                    _resource("example.com", "Domain", True),
                    _resource("https://example.com/admin", "Url", True),
                ]
            }
        )
    )

    assert result["complete"] is False
    assert result["allowed_targets"] == ["example.com"]
    assert result["unsupported"] == ["Url:https://example.com/admin"]
    assert result["campaign_created"] is False


def test_hackerone_scope_preview_api_rejects_partial_page():
    with pytest.raises(HTTPException) as exc:
        preview_hackerone_scope(
            HackerOneScopePreviewInput(
                document={
                    "data": [_resource("example.com", "Domain", True)],
                    "links": {"next": "https://api.hackerone.com/next"},
                }
            )
        )

    assert exc.value.status_code == 400
    assert "collect all pages" in str(exc.value.detail)


def test_hackerone_scope_preview_route_is_in_authenticated_api_namespace():
    schema = app.openapi()

    assert "/api/imports/hackerone/scope-preview" in schema["paths"]
    assert "post" in schema["paths"]["/api/imports/hackerone/scope-preview"]


def test_hackerone_scope_preview_input_requires_document():
    with pytest.raises(Exception):
        HackerOneScopePreviewInput()
