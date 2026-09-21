from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.hackerone_api as hackerone_api
from app.hackerone_api import router as hackerone_router
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


def _payload():
    return {
        "document": {"data": [_resource("example.com")]},
        "policy": {
            "authorization_reference": "H1-PROGRAM-42",
            "policy_version": "2026-09-16",
            "reviewed_at": "2026-09-16T14:00:00+02:00",
            "reviewed_by": "human-reviewer",
            "safe_harbor_confirmed": True,
            "automated_scanning": True,
            "max_requests_per_second": 1.0,
            "test_account_required": False,
            "test_account_constraints": "",
            "additional_restrictions": [],
            "program_notes": "Reviewed against the current program policy.",
        },
        "target": {
            "name": "Authorized HackerOne program",
            "primary_url": "https://example.com",
        },
    }


def test_hackerone_launch_creates_bound_running_campaign(tmp_path, monkeypatch):
    db = str(tmp_path / "launch.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")
    monkeypatch.setattr(
        hackerone_api,
        "_assert_hackerone_live_scan_ready",
        lambda: None,
    )

    api = FastAPI()
    api.include_router(hackerone_router)
    response = TestClient(api).post(
        "/api/imports/hackerone/campaigns/launch",
        json=_payload(),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "hackerone"
    assert result["campaign_created"] is True
    assert result["campaign"]["state"] == "running"
    assert result["start"]["state"] == "running"
    assert result["start"]["job"]["kind"] == "nuclei_scan"

    persisted = Storage(db, artifacts).get_campaign(result["campaign"]["id"])
    assert persisted is not None
    event_types = [event.get("type") for event in persisted["events"]]
    assert "hackerone_policy_bound" in event_types
    assert "campaign_started" in event_types
