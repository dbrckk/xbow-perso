from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.hackerone_api as hackerone_api
from app.hackerone_api import router


def _resource(identifier: str):
    return {
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": "Domain",
            "eligible_for_submission": True,
        },
    }


def _policy():
    return {
        "authorization_reference": "https://hackerone.com/acme",
        "policy_version": "2026-09-18",
        "reviewed_at": "2026-09-18T15:00:00+02:00",
        "reviewed_by": "operator",
        "safe_harbor_confirmed": True,
        "automated_scanning": True,
        "max_requests_per_second": 1.0,
        "test_account_required": False,
        "test_account_constraints": "",
        "additional_restrictions": [],
        "program_notes": "Reviewed manually.",
    }


def _api():
    api = FastAPI()
    api.include_router(router)
    return TestClient(api)


def _snapshot(document, sha="a" * 64):
    return SimpleNamespace(
        handle="acme",
        program={"handle": "acme", "name": "Acme", "policy": "Policy"},
        document=document,
        scope_exclusions=(),
        preview={"complete": True, "allowed_targets": ["example.com"], "assets": []},
        snapshot_sha256=sha,
    )


def test_bound_rules_preview_returns_verified_remote_binding(monkeypatch):
    document = {"data": [_resource("example.com")], "links": {}}
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(document),
    )

    response = _api().post(
        "/api/imports/hackerone/rules-preview",
        json={
            "document": document,
            "policy": _policy(),
            "remote_handle": "acme",
            "remote_snapshot_sha256": "a" * 64,
        },
    )

    assert response.status_code == 200
    assert response.json()["remote_binding"] == {
        "handle": "acme",
        "snapshot_sha256": "a" * 64,
        "verified": True,
    }


def test_remote_binding_must_be_complete():
    document = {"data": [_resource("example.com")], "links": {}}

    response = _api().post(
        "/api/imports/hackerone/rules-preview",
        json={
            "document": document,
            "policy": _policy(),
            "remote_handle": "acme",
        },
    )

    assert response.status_code == 422


def test_bound_preview_rejects_document_not_from_remote_snapshot(monkeypatch):
    remote_document = {"data": [_resource("example.com")], "links": {}}
    local_document = {"data": [_resource("other.example.com")], "links": {}}
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(remote_document),
    )

    response = _api().post(
        "/api/imports/hackerone/rules-preview",
        json={
            "document": local_document,
            "policy": _policy(),
            "remote_handle": "acme",
            "remote_snapshot_sha256": "a" * 64,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "hackerone_snapshot_document_mismatch"


def test_bound_launch_refetches_and_rejects_snapshot_drift(tmp_path, monkeypatch):
    document = {"data": [_resource("example.com")], "links": {}}
    monkeypatch.setenv("XBOW_DB_PATH", str(tmp_path / "drift.sqlite3"))
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(document, sha="b" * 64),
    )

    response = _api().post(
        "/api/imports/hackerone/campaigns/launch",
        json={
            "document": document,
            "policy": _policy(),
            "target": {
                "name": "Acme authorized program",
                "primary_url": "https://example.com",
            },
            "remote_handle": "acme",
            "remote_snapshot_sha256": "a" * 64,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "HackerOne remote snapshot changed; review again",
        "reason": "stale_hackerone_snapshot",
    }


def test_legacy_manual_preview_still_works_without_remote_binding():
    document = {"data": [_resource("example.com")], "links": {}}

    response = _api().post(
        "/api/imports/hackerone/rules-preview",
        json={"document": document, "policy": _policy()},
    )

    assert response.status_code == 200
    assert "remote_binding" not in response.json()
