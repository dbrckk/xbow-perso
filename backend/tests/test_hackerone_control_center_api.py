from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.hackerone_api as hackerone_api
from app.hackerone_api import router
from app.hackerone_client import HackerOneClientError


def _client():
    api = FastAPI()
    api.include_router(router)
    return TestClient(api)


def test_control_center_routes_exist():
    api = FastAPI()
    api.include_router(router)
    schema = api.openapi()
    assert "/api/imports/hackerone/connection" in schema["paths"]
    assert "/api/imports/hackerone/programs" in schema["paths"]
    assert "/api/imports/hackerone/programs/{handle}/snapshot" in schema["paths"]


def test_connection_reports_configured_without_exposing_credentials(monkeypatch):
    monkeypatch.setattr(
        hackerone_api,
        "load_hackerone_credentials",
        lambda: SimpleNamespace(username="hunter", token="secret-token-value"),
        raising=False,
    )

    response = _client().get("/api/imports/hackerone/connection")

    assert response.status_code == 200
    assert response.json() == {"provider": "hackerone", "configured": True}
    encoded = response.text
    assert "hunter" not in encoded
    assert "secret-token-value" not in encoded


def test_connection_reports_unconfigured_safely(monkeypatch):
    def fail():
        raise HackerOneClientError("credentials are not configured")

    monkeypatch.setattr(hackerone_api, "load_hackerone_credentials", fail, raising=False)

    response = _client().get("/api/imports/hackerone/connection")

    assert response.status_code == 200
    assert response.json() == {"provider": "hackerone", "configured": False}


def test_programs_returns_normalized_safe_metadata(monkeypatch):
    class FakeClient:
        def get_all_pages(self, path):
            assert path == "hackers/programs"
            return [
                {
                    "type": "program",
                    "id": "42",
                    "attributes": {
                        "handle": "acme",
                        "name": "Acme Security",
                        "submission_state": "open",
                        "state": "public_mode",
                        "offers_bounties": True,
                        "gold_standard_safe_harbor": True,
                        "policy": "must not be returned in list",
                    },
                }
            ]

    monkeypatch.setattr(hackerone_api, "HackerOneClient", FakeClient, raising=False)

    response = _client().get("/api/imports/hackerone/programs")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "hackerone",
        "programs": [
            {
                "handle": "acme",
                "name": "Acme Security",
                "submission_state": "open",
                "state": "public_mode",
                "offers_bounties": True,
                "gold_standard_safe_harbor": True,
            }
        ],
    }
    assert "must not be returned" not in response.text


def test_snapshot_route_returns_remote_binding_data(monkeypatch):
    snapshot = SimpleNamespace(
        handle="acme",
        program={"handle": "acme", "name": "Acme Security", "policy": "Policy"},
        document={"data": [], "links": {}},
        scope_exclusions=({"id": "ex-1", "attributes": {"details": "No status page"}},),
        preview={"complete": True, "allowed_targets": ["app.example.com"], "assets": []},
        snapshot_sha256="a" * 64,
    )
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: snapshot,
        raising=False,
    )

    response = _client().get("/api/imports/hackerone/programs/acme/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "hackerone"
    assert body["handle"] == "acme"
    assert body["snapshot_sha256"] == "a" * 64
    assert body["document"] == {"data": [], "links": {}}
    assert body["scope_exclusions"][0]["id"] == "ex-1"


def test_upstream_auth_error_is_mapped_without_leaking_detail(monkeypatch):
    class FailingClient:
        def get_all_pages(self, path):
            raise HackerOneClientError("HackerOne returned HTTP 401 secret detail", status_code=401)

    monkeypatch.setattr(hackerone_api, "HackerOneClient", FailingClient, raising=False)

    response = _client().get("/api/imports/hackerone/programs")

    assert response.status_code == 502
    assert response.json()["detail"] == "HackerOne upstream authentication failed"
    assert "secret detail" not in response.text


def test_upstream_rate_limit_is_service_unavailable(monkeypatch):
    class FailingClient:
        def get_all_pages(self, path):
            raise HackerOneClientError("HackerOne returned HTTP 429", status_code=429)

    monkeypatch.setattr(hackerone_api, "HackerOneClient", FailingClient, raising=False)

    response = _client().get("/api/imports/hackerone/programs")

    assert response.status_code == 503
    assert response.json()["detail"] == "HackerOne upstream temporarily unavailable"
