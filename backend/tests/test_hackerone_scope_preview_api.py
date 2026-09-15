import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.hackerone_api import (
    HackerOneProgramPolicyInput,
    HackerOneRulesPreviewInput,
    preview_hackerone_rules,
    router as hackerone_router,
)
from app.main import HackerOneScopePreviewInput, app, preview_hackerone_scope
from app.storage import Storage


def _resource(identifier: str, asset_type: str, eligible: bool):
    return {
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": asset_type,
            "eligible_for_submission": eligible,
        },
    }


def _policy_values(**overrides):
    values = {
        "authorization_reference": "H1-PROGRAM-42",
        "policy_version": "2026-09-15",
        "reviewed_at": "2026-09-15T20:00:00+02:00",
        "reviewed_by": "human-reviewer",
        "safe_harbor_confirmed": True,
        "automated_scanning": False,
        "max_requests_per_second": 1.25,
        "test_account_required": False,
        "test_account_constraints": "",
        "additional_restrictions": ["Do not access unrelated customer data"],
        "program_notes": "Reviewed against the current HackerOne program policy.",
    }
    values.update(overrides)
    return values


def _policy_input(**overrides):
    return HackerOneProgramPolicyInput(**_policy_values(**overrides))


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


def test_hackerone_rules_preview_requires_explicit_policy_and_does_not_persist():
    payload = HackerOneRulesPreviewInput(
        document={
            "data": [
                _resource("example.com", "Domain", True),
                _resource("blocked.example.com", "Domain", False),
            ]
        },
        policy=_policy_input(),
    )

    result = preview_hackerone_rules(payload)

    assert result["provider"] == "hackerone"
    assert result["complete"] is True
    assert result["requires_review"] is True
    assert result["persisted"] is False
    assert result["campaign_created"] is False
    assert result["policy_snapshot"] == {
        "authorization_reference": "H1-PROGRAM-42",
        "policy_version": "2026-09-15",
        "reviewed_at": "2026-09-15T18:00:00+00:00",
        "reviewed_by": "human-reviewer",
        "safe_harbor_confirmed": True,
        "automated_scanning": False,
        "max_requests_per_second": 1.25,
        "test_account_required": False,
        "test_account_constraints": "",
        "additional_restrictions": ["Do not access unrelated customer data"],
        "program_notes": "Reviewed against the current HackerOne program policy.",
    }
    assert result["rules"] == {
        "authorization_reference": "H1-PROGRAM-42",
        "allowed_targets": ["example.com"],
        "denied_targets": ["blocked.example.com"],
        "max_requests_per_second": 1.25,
        "destructive_testing": False,
        "denial_of_service": False,
        "social_engineering": False,
        "credential_attacks": False,
        "automated_scanning": False,
        "notes": (
            "Imported from HackerOne StructuredScope with explicit HackerOne "
            "program policy 2026-09-15; destructive, denial-of-service, "
            "social-engineering, and credential-attack capabilities remain disabled."
        ),
    }


@pytest.mark.parametrize("missing", ["automated_scanning", "max_requests_per_second"])
def test_hackerone_rules_preview_has_no_automation_or_rate_defaults(missing):
    policy = _policy_values()
    policy.pop(missing)

    with pytest.raises(ValidationError):
        HackerOneRulesPreviewInput(
            document={"data": [_resource("example.com", "Domain", True)]},
            policy=policy,
        )


@pytest.mark.parametrize(
    "missing",
    [
        "policy_version",
        "reviewed_at",
        "reviewed_by",
        "safe_harbor_confirmed",
        "test_account_required",
        "test_account_constraints",
        "additional_restrictions",
        "program_notes",
    ],
)
def test_hackerone_policy_requires_review_metadata_before_rules_preview(missing):
    policy = _policy_values()
    policy.pop(missing)

    with pytest.raises(ValidationError):
        HackerOneProgramPolicyInput(**policy)


def test_hackerone_policy_rejects_naive_review_timestamp():
    with pytest.raises(ValidationError, match="timezone"):
        _policy_input(reviewed_at="2026-09-15T20:00:00")


def test_hackerone_policy_rejects_implicit_boolean_request_rate():
    with pytest.raises(ValidationError, match="explicit number"):
        _policy_input(max_requests_per_second=True)


def test_hackerone_rules_preview_rejects_unsupported_scope_fail_closed():
    payload = HackerOneRulesPreviewInput(
        document={
            "data": [
                _resource("example.com", "Domain", True),
                _resource("https://example.com/admin", "Url", True),
            ]
        },
        policy=_policy_input(max_requests_per_second=1.0),
    )

    with pytest.raises(HTTPException) as exc:
        preview_hackerone_rules(payload)

    assert exc.value.status_code == 400
    assert "cannot be converted" in str(exc.value.detail)


def test_hackerone_rules_preview_route_is_in_authenticated_api_namespace():
    schema = app.openapi()

    assert "/api/imports/hackerone/rules-preview" in schema["paths"]
    assert "post" in schema["paths"]["/api/imports/hackerone/rules-preview"]


def test_hackerone_conservative_campaign_admission_route_exists():
    schema = app.openapi()

    assert "/api/imports/hackerone/campaigns" in schema["paths"]
    assert "post" in schema["paths"]["/api/imports/hackerone/campaigns"]


def test_hackerone_conservative_admission_persists_policy_binding(tmp_path, monkeypatch):
    db = str(tmp_path / "hackerone.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    api = FastAPI()
    api.include_router(hackerone_router)
    client = TestClient(api)
    response = client.post(
        "/api/imports/hackerone/campaigns",
        json={
            "document": {"data": [_resource("example.com", "Domain", True)]},
            "policy": _policy_values(
                automated_scanning=True,
                additional_restrictions=[],
            ),
            "target": {
                "name": "HackerOne fixture",
                "primary_url": "https://example.com",
            },
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "hackerone"
    assert result["campaign_created"] is True
    assert result["campaign"]["state"] == "ready"
    assert len(result["policy_binding"]["policy_snapshot_sha256"]) == 64
    assert len(result["policy_binding"]["binding_fingerprint"]) == 64

    persisted = Storage(db, artifacts).get_campaign(result["campaign"]["id"])
    assert persisted is not None
    bound = [event for event in persisted["events"] if event.get("type") == "hackerone_policy_bound"]
    assert len(bound) == 1
    assert bound[0]["provider"] == "hackerone"
    assert bound[0]["mode"] == "conservative"
    assert bound[0]["policy_snapshot_sha256"] == result["policy_binding"]["policy_snapshot_sha256"]
    assert bound[0]["binding_fingerprint"] == result["policy_binding"]["binding_fingerprint"]


@pytest.mark.parametrize(
    ("policy_overrides", "reason"),
    [
        ({"safe_harbor_confirmed": False}, "safe_harbor_required"),
        ({"automated_scanning": False}, "automated_scanning_not_authorized"),
        (
            {
                "test_account_required": True,
                "test_account_constraints": "Use program-issued account only",
            },
            "test_account_workflow_not_supported",
        ),
        (
            {"test_account_constraints": "Use a dedicated tenant"},
            "test_account_constraints_not_supported",
        ),
        (
            {"additional_restrictions": ["Do not access customer records"]},
            "additional_restrictions_require_manual_enforcement",
        ),
    ],
)
def test_hackerone_conservative_admission_blocks_nontrivial_policy(
    tmp_path,
    monkeypatch,
    policy_overrides,
    reason,
):
    db = str(tmp_path / "blocked.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    api = FastAPI()
    api.include_router(hackerone_router)
    client = TestClient(api)
    admission_policy = {
        "automated_scanning": True,
        "additional_restrictions": [],
    }
    admission_policy.update(policy_overrides)
    response = client.post(
        "/api/imports/hackerone/campaigns",
        json={
            "document": {"data": [_resource("example.com", "Domain", True)]},
            "policy": _policy_values(**admission_policy),
            "target": {
                "name": "HackerOne blocked fixture",
                "primary_url": "https://example.com",
            },
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "HackerOne conservative admission blocked",
        "reason": reason,
    }
    assert Storage(db, artifacts).list_campaigns() == []
