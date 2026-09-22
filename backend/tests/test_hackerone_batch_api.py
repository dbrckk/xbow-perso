from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.hackerone_api as hackerone_api
from app.hackerone_client import HackerOneProgramSnapshot
from app.jobqueue import JobQueue
from app.storage import Storage


def _resource(identifier: str):
    return {
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": "Domain",
            "eligible_for_submission": True,
        },
    }


def _snapshot(handle: str, domain: str, fingerprint: str):
    document = {"data": [_resource(domain)], "links": {}}
    return HackerOneProgramSnapshot(
        handle=handle,
        program={
            "name": handle.replace("-", " ").title(),
            "handle": handle,
            "policy": "Authorized automated scanning for this fixture.",
            "submission_state": "open",
            "state": "public_mode",
            "offers_bounties": True,
            "gold_standard_safe_harbor": True,
        },
        document=document,
        scope_exclusions=(),
        preview={
            "complete": True,
            "allowed_targets": [domain],
            "denied_targets": [],
            "conflicts": [],
            "unsupported": [],
            "assets": [],
        },
        snapshot_sha256=fingerprint,
    )


def _campaign_payload(handle: str, domain: str, fingerprint: str):
    return {
        "document": {"data": [_resource(domain)], "links": {}},
        "policy": {
            "authorization_reference": f"https://hackerone.com/{handle}?type=team",
            "policy_version": "2026-09-20",
            "reviewed_at": "2026-09-20T12:00:00+00:00",
            "reviewed_by": "human-reviewer",
            "safe_harbor_confirmed": True,
            "automated_scanning": True,
            "max_requests_per_second": 1.0,
            "test_account_required": False,
            "test_account_constraints": "",
            "additional_restrictions": [],
            "program_notes": "Fixture review.",
        },
        "target": {
            "name": handle,
            "primary_url": f"https://{domain}",
        },
        "remote_handle": handle,
        "remote_snapshot_sha256": fingerprint,
    }


def test_sequential_batch_persists_and_starts_only_first_member(tmp_path, monkeypatch):
    db = str(tmp_path / "batch.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")

    snapshots = {
        "program-one": _snapshot("program-one", "one.example.com", "a" * 64),
        "program-two": _snapshot("program-two", "two.example.com", "b" * 64),
    }
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: snapshots[handle],
    )
    monkeypatch.setattr(
        "app.hackerone_client.fetch_hackerone_program_snapshot",
        lambda handle: snapshots[handle],
    )

    api = FastAPI()
    api.include_router(hackerone_api.router)
    response = TestClient(api).post(
        "/api/imports/hackerone/batches/launch",
        json={
            "mode": "sequential",
            "campaigns": [
                _campaign_payload("program-one", "one.example.com", "a" * 64),
                _campaign_payload("program-two", "two.example.com", "b" * 64),
            ],
        },
    )

    assert response.status_code == 200, response.text
    batch = response.json()
    assert batch["mode"] == "sequential"
    assert batch["state"] == "running"
    assert [member["status"] for member in batch["members"]] == ["running", "ready"]
    assert batch["continues_without_dashboard"] is True
    assert batch["automatic_submission"] is False

    store = Storage(db, artifacts)
    persisted = store.get_hackerone_batch(batch["id"])
    assert persisted is not None
    assert len(persisted["members"]) == 2

    jobs = JobQueue(db)
    assert jobs.campaign_job_status_counts(batch["members"][0]["campaign_id"])["queued"] == 2
    assert jobs.campaign_job_status_counts(batch["members"][1]["campaign_id"])["queued"] == 0


def test_batch_rejects_unbound_campaigns():
    api = FastAPI()
    api.include_router(hackerone_api.router)
    payload = _campaign_payload("program-one", "one.example.com", "a" * 64)
    payload.pop("remote_handle")
    payload.pop("remote_snapshot_sha256")

    response = TestClient(api).post(
        "/api/imports/hackerone/batches/launch",
        json={"mode": "sequential", "campaigns": [payload]},
    )

    assert response.status_code == 422


def test_generic_batch_launch_rejects_when_another_batch_is_active(tmp_path, monkeypatch):
    db = str(tmp_path / "generic-active.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")

    store = Storage(db, artifacts)
    store.save_hackerone_batch(
        {
            "id": "already-running",
            "provider": "hackerone",
            "mode": "parallel",
            "state": "running",
            "members": [],
            "summary": {},
            "created_at": "2026-09-22T13:00:00+00:00",
            "updated_at": "2026-09-22T13:00:00+00:00",
        },
        expected_version=0,
    )

    api = FastAPI()
    api.include_router(hackerone_api.router)
    response = TestClient(api).post(
        "/api/imports/hackerone/batches/launch",
        json={
            "mode": "sequential",
            "campaigns": [
                _campaign_payload("program-one", "one.example.com", "a" * 64)
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "active_batch_exists"
    assert response.json()["detail"]["batch_id"] == "already-running"
    assert store.list_campaigns() == []
