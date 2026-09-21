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
            "policy": "fixture policy",
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


def _profile(handle: str, domain: str, fingerprint: str):
    return {
        "id": f"{handle}@{fingerprint}",
        "provider": "hackerone",
        "handle": handle,
        "snapshot_sha256": fingerprint,
        "preferred_primary_url": f"https://{domain}/",
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
        "policy_snapshot_sha256": "f" * 64,
        "saved_at": "2026-09-20T12:00:00+00:00",
        "updated_at": "2026-09-20T12:00:00+00:00",
        "contains_secrets": False,
    }


def _app():
    api = FastAPI()
    api.include_router(hackerone_api.router)
    return TestClient(api)


def test_reviewed_batch_launch_needs_only_handles(tmp_path, monkeypatch):
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
    monkeypatch.setattr(
        hackerone_api,
        "hackerone_batch_go_no_go",
        lambda _payload: {"go": True, "blockers": []},
    )

    store = Storage(db, artifacts)
    store.save_hackerone_review_profile(
        _profile("program-one", "one.example.com", "a" * 64),
        expected_version=0,
    )
    store.save_hackerone_review_profile(
        _profile("program-two", "two.example.com", "b" * 64),
        expected_version=0,
    )

    response = _app().post(
        "/api/imports/hackerone/batches/launch-reviewed",
        json={
            "mode": "sequential",
            "handles": ["program-one", "program-two"],
        },
    )

    assert response.status_code == 200, response.text
    batch = response.json()
    assert batch["mode"] == "sequential"
    assert [member["handle"] for member in batch["members"]] == [
        "program-one",
        "program-two",
    ]
    assert [member["status"] for member in batch["members"]] == [
        "running",
        "ready",
    ]

    jobs = JobQueue(db)
    assert (
        jobs.campaign_job_status_counts(batch["members"][0]["campaign_id"])[
            "queued"
        ]
        == 1
    )
    assert (
        jobs.campaign_job_status_counts(batch["members"][1]["campaign_id"])[
            "queued"
        ]
        == 0
    )


def test_reviewed_batch_rejects_changed_fingerprint_before_creating_campaigns(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "stale.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")

    store = Storage(db, artifacts)
    store.save_hackerone_review_profile(
        _profile("program-one", "one.example.com", "a" * 64),
        expected_version=0,
    )

    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: _snapshot(handle, "one.example.com", "b" * 64),
    )

    response = _app().post(
        "/api/imports/hackerone/batches/launch-reviewed",
        json={"mode": "sequential", "handles": ["program-one"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "HackerOne reviewed profile required",
        "reason": "review_profile_required",
        "handles": ["program-one"],
    }
    assert store.list_campaigns() == []
    assert store.list_hackerone_batches(limit=10) == []


def test_reviewed_batch_collects_all_missing_profiles_before_admission(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "missing.sqlite3")
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

    store = Storage(db, artifacts)
    response = _app().post(
        "/api/imports/hackerone/batches/launch-reviewed",
        json={
            "mode": "parallel",
            "handles": ["program-one", "program-two"],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "HackerOne reviewed profile required",
        "reason": "review_profile_required",
        "handles": ["program-one", "program-two"],
    }
    assert store.list_campaigns() == []


def test_reviewed_batch_rejects_duplicate_handles():
    response = _app().post(
        "/api/imports/hackerone/batches/launch-reviewed",
        json={
            "mode": "sequential",
            "handles": ["program-one", "program-one"],
        },
    )

    assert response.status_code == 422
