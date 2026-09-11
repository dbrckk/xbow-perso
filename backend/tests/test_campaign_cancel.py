import pytest

from app.jobqueue import JobQueue
from app.main import Campaign, CampaignState, Finding, ProgramRules, TargetInput, add_finding, cancel_campaign, queue_report, validate_finding
from app.storage import Storage
from app.worker_service import _campaign as load_worker_campaign, process_one


def _setup(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    campaign = Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        state=CampaignState.running,
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    return db, store, campaign


def test_cancel_campaign_cancels_queued_jobs_but_preserves_running_lease(tmp_path, monkeypatch):
    db, store, campaign = _setup(tmp_path, monkeypatch)
    jobs = JobQueue(db)

    running = jobs.enqueue(campaign.id, "report", {"campaign_id": campaign.id}, dedupe_key="running")
    claimed = jobs.claim("worker-a")
    assert claimed is not None
    assert claimed["id"] == running["id"]

    queued = jobs.enqueue(
        campaign.id,
        "independent_validation",
        {"campaign_id": campaign.id, "finding_id": "f1", "asset": "https://example.test"},
        dedupe_key="queued",
    )

    result = cancel_campaign(campaign.id)

    assert result["state"] == CampaignState.cancelled
    assert result["cancelled_queued_jobs"] == 1
    assert result["running_jobs"] == 1
    assert result["running_jobs_not_forcibly_terminated"] is True
    assert jobs.get(queued["id"])["status"] == "cancelled"
    assert jobs.get(running["id"])["status"] == "running"
    assert store.get_campaign(campaign.id)["state"] == "cancelled"


def test_cancel_campaign_is_idempotent(tmp_path, monkeypatch):
    _db, store, campaign = _setup(tmp_path, monkeypatch)

    first = cancel_campaign(campaign.id)
    second = cancel_campaign(campaign.id)

    assert first["state"] == CampaignState.cancelled
    assert second["state"] == CampaignState.cancelled
    events = [
        event
        for event in store.get_campaign(campaign.id)["events"]
        if event.get("type") == "campaign_cancelled"
    ]
    assert len(events) == 1


def test_worker_refuses_cancelled_campaign(tmp_path, monkeypatch):
    _db, store, campaign = _setup(tmp_path, monkeypatch)
    cancel_campaign(campaign.id)

    with pytest.raises(ValueError, match="campaign is cancelled"):
        load_worker_campaign(store, campaign.id)


def test_completed_campaign_cannot_be_cancelled(tmp_path, monkeypatch):
    _db, store, campaign = _setup(tmp_path, monkeypatch)
    document, version = store.get_campaign_record(campaign.id)
    document["state"] = "completed"
    store.save_campaign(document, expected_version=version)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        cancel_campaign(campaign.id)

    assert exc.value.status_code == 409


def test_running_job_becomes_cancelled_when_worker_observes_cancelled_campaign(tmp_path, monkeypatch):
    db, store, campaign = _setup(tmp_path, monkeypatch)
    jobs = JobQueue(db)
    job = jobs.enqueue(campaign.id, "report", {"campaign_id": campaign.id}, max_attempts=2)
    claimed = jobs.claim("worker-a")
    assert claimed is not None and claimed["id"] == job["id"]

    document, version = store.get_campaign_record(campaign.id)
    document["state"] = "cancelled"
    store.save_campaign(document, expected_version=version)

    # Put the claimed job back into the worker path without allowing a retry loop.
    with jobs.connect() as conn:
        conn.execute(
            "UPDATE jobs SET status='queued', claimed_by=NULL, claimed_at=NULL, attempts=0 WHERE id=?",
            (job["id"],),
        )

    assert process_one(jobs, store, "worker-a") is True
    final = jobs.get(job["id"])
    assert final is not None
    assert final["status"] == "cancelled"
    assert final["attempts"] == 1
    assert final["claimed_by"] is None


def test_cancelled_campaign_rejects_new_mutations(tmp_path, monkeypatch):
    _db, _store, campaign = _setup(tmp_path, monkeypatch)
    cancel_campaign(campaign.id)

    candidate = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        discovered_by="scanner",
    )

    from fastapi import HTTPException

    for operation in (
        lambda: add_finding(campaign.id, candidate),
        lambda: validate_finding(campaign.id, "f1", True, "human-reviewer"),
        lambda: queue_report(campaign.id),
    ):
        with pytest.raises(HTTPException) as exc:
            operation()
        assert exc.value.status_code == 409
        assert "cancelled" in str(exc.value.detail).lower()
