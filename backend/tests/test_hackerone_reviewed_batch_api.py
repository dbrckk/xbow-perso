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


def _snapshot(handle: str, domain: str, fingerprint: str, *, scope_exclusions=()):
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
        scope_exclusions=tuple(scope_exclusions),
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
    fetch_calls = []
    def fetch_snapshot(handle):
        fetch_calls.append(handle)
        return snapshots[handle]

    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        fetch_snapshot,
    )
    monkeypatch.setattr(
        "app.hackerone_client.fetch_hackerone_program_snapshot",
        lambda handle: snapshots[handle],
    )
    monkeypatch.setattr(
        hackerone_api,
        "_runtime_prelaunch_verdict",
        lambda: {"runtime_ready": True, "runtime": {}, "blockers": []},
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
    assert fetch_calls == ["program-one", "program-two"]

    jobs = JobQueue(db)
    assert (
        jobs.campaign_job_status_counts(batch["members"][0]["campaign_id"])[
            "queued"
        ]
        == 2
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


def test_preverified_internal_admission_rejects_binding_mismatch(tmp_path, monkeypatch):
    db = str(tmp_path / "binding-mismatch.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    payload = hackerone_api.HackerOneCampaignAdmissionInput(
        document={"data": [_resource("example.com")], "links": {}},
        policy=hackerone_api.HackerOneProgramPolicyInput(
            authorization_reference="https://hackerone.com/example",
            policy_version="fixture",
            reviewed_at="2026-09-22T12:00:00+00:00",
            reviewed_by="test",
            safe_harbor_confirmed=True,
            automated_scanning=True,
            max_requests_per_second=1.0,
            test_account_required=False,
            test_account_constraints="",
            additional_restrictions=[],
            program_notes="fixture",
        ),
        target=hackerone_api.HackerOneCampaignTargetInput(
            name="Example",
            primary_url="https://example.com",
        ),
        remote_handle="example",
        remote_snapshot_sha256="a" * 64,
    )

    try:
        hackerone_api._admit_hackerone_campaign_impl(
            payload,
            verified_remote_binding={
                "handle": "other",
                "snapshot_sha256": "a" * 64,
                "verified": True,
            },
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 500
    else:
        raise AssertionError("mismatched internal binding should be rejected")


def test_reviewed_batch_rejects_new_launch_when_another_batch_is_active(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "active-batch.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")

    store = Storage(db, artifacts)
    store.save_hackerone_batch(
        {
            "id": "active-batch",
            "provider": "hackerone",
            "mode": "parallel",
            "state": "running",
            "members": [
                {
                    "index": 0,
                    "campaign_id": "existing-campaign",
                    "handle": "existing-program",
                    "snapshot_sha256": "a" * 64,
                    "status": "running",
                    "reason": None,
                }
            ],
            "summary": {"running": 1},
            "created_at": "2026-09-22T13:00:00+00:00",
            "updated_at": "2026-09-22T13:00:00+00:00",
        },
        expected_version=0,
    )

    response = _app().post(
        "/api/imports/hackerone/batches/launch-reviewed",
        json={"mode": "parallel", "handles": ["program-one"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "message": "A HackerOne batch is already active",
        "reason": "active_batch_exists",
        "batch_id": "active-batch",
    }
    assert store.list_campaigns() == []


def test_reviewed_batch_rejects_unenforced_scope_exclusions_before_campaign_creation(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "scope-exclusion.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")

    fingerprint = "a" * 64
    snapshot = _snapshot(
        "program-one",
        "one.example.com",
        fingerprint,
        scope_exclusions=(
            {
                "id": "exclude-1",
                "type": "scope-exclusion",
                "attributes": {
                    "category": "other",
                    "details": "Do not test status.example.com",
                },
            },
        ),
    )
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: snapshot,
    )

    store = Storage(db, artifacts)
    store.save_hackerone_review_profile(
        _profile("program-one", "one.example.com", fingerprint),
        expected_version=0,
    )

    response = _app().post(
        "/api/imports/hackerone/batches/launch-reviewed",
        json={"mode": "sequential", "handles": ["program-one"]},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["reason"] == "scope_exclusions_require_manual_enforcement"
    assert detail["handles"] == ["program-one"]
    assert store.list_campaigns() == []
    assert store.list_hackerone_batches(limit=10) == []


def test_reviewed_batch_rejects_saved_policy_that_disables_automation(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "automation-disabled.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")

    fingerprint = "a" * 64
    snapshot = _snapshot("program-one", "one.example.com", fingerprint)
    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda handle: snapshot,
    )

    profile = _profile("program-one", "one.example.com", fingerprint)
    profile["policy"]["automated_scanning"] = False
    store = Storage(db, artifacts)
    store.save_hackerone_review_profile(profile, expected_version=0)

    response = _app().post(
        "/api/imports/hackerone/batches/launch-reviewed",
        json={"mode": "sequential", "handles": ["program-one"]},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["reason"] == "automated_scanning_not_authorized"
    assert detail["handles"] == ["program-one"]
    assert store.list_campaigns() == []


def test_v81_happy_path_review_package_to_profile_to_launch(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "v81-e2e.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")

    def review_snapshot(handle: str, domain: str, fingerprint: str):
        document = {"data": [_resource(domain)], "links": {}}
        return HackerOneProgramSnapshot(
            handle=handle,
            program={
                "name": handle.replace("-", " ").title(),
                "handle": handle,
                "policy": "Automated scanning is allowed within the listed scope.",
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
                "assets": [
                    {
                        "identifier": domain,
                        "asset_type": "Domain",
                        "eligible_for_submission": True,
                        "compatible": True,
                    }
                ],
            },
            snapshot_sha256=fingerprint,
        )

    snapshots = {
        "program-one": review_snapshot("program-one", "one.example.com", "a" * 64),
        "program-two": review_snapshot("program-two", "two.example.com", "b" * 64),
    }

    def fake_selection(exclude=""):
        excluded={value for value in exclude.split(",") if value}
        handles=[
            handle
            for handle in ["program-one", "program-two", "x3", "x4", "x5", "x6"]
            if handle not in excluded
        ]
        items=[]
        for handle in handles[:6]:
            items.append(
                {
                    "handle": handle,
                    "name": handle.replace("-", " ").title(),
                    "status": "REVIEW",
                    "offers_bounties": True,
                    "gold_standard_safe_harbor": True,
                    "effort_factor": 1.0,
                    "value_efficiency_score": 80,
                    "opportunity_score": 80,
                    "historical_usd_awarded_max": 1000,
                    "historical_value_score": 50,
                }
            )
        return {
            "provider": "hackerone",
            "groups": {"easy": items[:2], "medium": items[2:4], "high_value": items[4:6]},
            "selection": items,
            "handles": [item["handle"] for item in items],
            "complete": len(items) == 6,
            "selection_count": len(items),
            "ready_count": 0,
            "review_count": len(items),
            "revalidation_count": 0,
            "launch_ready": False,
            "catalog_source": "local-cache",
        }

    def fetch_snapshot(handle):
        if handle in snapshots:
            return snapshots[handle]
        return review_snapshot(handle, f"{handle}.example.com", (handle[0] * 64)[:64])

    monkeypatch.setattr(hackerone_api, "hackerone_simple_selection", fake_selection)
    monkeypatch.setattr(hackerone_api, "fetch_hackerone_program_snapshot", fetch_snapshot)
    monkeypatch.setattr(
        "app.hackerone_client.fetch_hackerone_program_snapshot",
        fetch_snapshot,
    )
    monkeypatch.setattr(
        hackerone_api,
        "_runtime_prelaunch_verdict",
        lambda: {"runtime_ready": True, "runtime": {}, "blockers": []},
    )

    package = hackerone_api.hackerone_simple_review_package()
    assert package["handles"] == ["program-one"]
    assert package["review_count"] == 1
    assert package["live_verified"] is True
    assert len(package["review_drafts"]) == 1

    client = _app()
    for draft in package["review_drafts"]:
        response = client.post(
            "/api/imports/hackerone/rules-preview",
            json={
                "document": draft["prefill"]["scope_document"],
                "policy": {
                    "authorization_reference": draft["prefill"]["authorization_reference"],
                    "policy_version": draft["prefill"]["policy_version"],
                    "reviewed_at": "2026-09-23T12:00:00+00:00",
                    "reviewed_by": "v81-e2e-test",
                    "safe_harbor_confirmed": True,
                    "automated_scanning": True,
                    "max_requests_per_second": 1.0,
                    "test_account_required": False,
                    "test_account_constraints": "",
                    "additional_restrictions": [],
                    "program_notes": "Conservative E2E test profile.",
                },
                "remote_handle": draft["handle"],
                "remote_snapshot_sha256": draft["snapshot_sha256"],
                "remember_review_profile": True,
                "preferred_primary_url": draft["prefill"]["primary_url"],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["review_profile_persisted"] is True
        assert body["complete"] is True

    launch = client.post(
        "/api/imports/hackerone/batches/launch-reviewed",
        json={
            "mode": "sequential",
            "handles": package["handles"],
        },
    )
    assert launch.status_code == 200, launch.text
    batch = launch.json()
    assert [member["handle"] for member in batch["members"]] == package["handles"]
    assert [member["status"] for member in batch["members"]] == ["running"]

    jobs = JobQueue(db)
    first_counts = jobs.campaign_job_status_counts(batch["members"][0]["campaign_id"])
    assert first_counts["queued"] >= 1
