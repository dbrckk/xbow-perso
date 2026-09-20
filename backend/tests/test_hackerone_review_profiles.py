from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.hackerone_api as hackerone_api
from app.storage import Storage


def _resource(identifier: str, eligible: bool = True):
    return {
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": "Domain",
            "eligible_for_submission": eligible,
        },
    }


def _policy(**overrides):
    value = {
        "authorization_reference": "https://hackerone.com/acme?type=team",
        "policy_version": "2026-09-20",
        "reviewed_at": "2026-09-20T12:00:00+00:00",
        "reviewed_by": "human-reviewer",
        "safe_harbor_confirmed": True,
        "automated_scanning": True,
        "max_requests_per_second": 1.0,
        "test_account_required": False,
        "test_account_constraints": "",
        "additional_restrictions": [],
        "program_notes": "Reviewed against current program policy.",
    }
    value.update(overrides)
    return value


def _snapshot(document, fingerprint="a" * 64):
    return SimpleNamespace(
        handle="acme",
        snapshot_sha256=fingerprint,
        document=document,
        program={"handle": "acme", "name": "Acme", "policy": "hidden"},
        scope_exclusions=(),
        preview={"complete": True, "assets": []},
    )


def _client():
    api = FastAPI()
    api.include_router(hackerone_api.router)
    return TestClient(api)


def test_rules_preview_can_persist_exact_review_profile(tmp_path, monkeypatch):
    db = str(tmp_path / "profiles.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    document = {"data": [_resource("example.com")], "links": {}}
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(document),
    )

    response = _client().post(
        "/api/imports/hackerone/rules-preview",
        json={
            "document": document,
            "policy": _policy(),
            "remote_handle": "acme",
            "remote_snapshot_sha256": "a" * 64,
            "remember_review_profile": True,
            "preferred_primary_url": "https://example.com",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_profile_persisted"] is True
    assert body["review_profile_persist_reason"] is None

    profile = Storage(db, artifacts).get_hackerone_review_profile(
        "acme@" + ("a" * 64)
    )
    assert profile is not None
    assert profile["handle"] == "acme"
    assert profile["snapshot_sha256"] == "a" * 64
    assert profile["preferred_primary_url"] == "https://example.com/"
    assert profile["policy"]["reviewed_at"] == "2026-09-20T12:00:00+00:00"
    assert profile["policy"]["automated_scanning"] is True
    assert profile["contains_secrets"] is False
    assert "document" not in profile
    assert "token" not in str(profile).lower()


def test_review_profile_list_is_redacted_and_read_only(tmp_path, monkeypatch):
    db = str(tmp_path / "profiles.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    store = Storage(db, artifacts)
    store.save_hackerone_review_profile(
        {
            "id": "acme@" + ("a" * 64),
            "provider": "hackerone",
            "handle": "acme",
            "snapshot_sha256": "a" * 64,
            "preferred_primary_url": "https://example.com/",
            "policy": _policy(),
            "policy_snapshot_sha256": "b" * 64,
            "saved_at": "2026-09-20T12:00:00+00:00",
            "updated_at": "2026-09-20T12:00:00+00:00",
            "contains_secrets": False,
        },
        expected_version=0,
    )

    response = _client().get("/api/imports/hackerone/review-profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["read_only"] is True
    assert body["contains_secrets"] is False
    assert len(body["profiles"]) == 1
    assert body["profiles"][0]["id"] == "acme@" + ("a" * 64)


def test_review_profile_requires_target_inside_reviewed_scope(tmp_path, monkeypatch):
    db = str(tmp_path / "profiles.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    document = {"data": [_resource("example.com")], "links": {}}
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(document),
    )

    response = _client().post(
        "/api/imports/hackerone/rules-preview",
        json={
            "document": document,
            "policy": _policy(),
            "remote_handle": "acme",
            "remote_snapshot_sha256": "a" * 64,
            "remember_review_profile": True,
            "preferred_primary_url": "https://outside.example.net",
        },
    )

    assert response.status_code == 400
    assert Storage(db, artifacts).list_hackerone_review_profiles() == []


def test_non_admissible_preview_is_not_remembered(tmp_path, monkeypatch):
    db = str(tmp_path / "profiles.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    document = {"data": [_resource("example.com")], "links": {}}
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(document),
    )

    response = _client().post(
        "/api/imports/hackerone/rules-preview",
        json={
            "document": document,
            "policy": _policy(automated_scanning=False),
            "remote_handle": "acme",
            "remote_snapshot_sha256": "a" * 64,
            "remember_review_profile": True,
            "preferred_primary_url": "https://example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_profile_persisted"] is False
    assert body["review_profile_persist_reason"] == "automated_scanning_not_authorized"
    assert Storage(db, artifacts).list_hackerone_review_profiles() == []
