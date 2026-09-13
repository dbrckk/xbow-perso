import pytest

from app.jobqueue import JobQueue
from app.main import Campaign, CampaignState, Finding, ProgramRules, TargetInput
from app.storage import CampaignConflictError, Storage
from app.validator import ValidationPolicyError
from app.worker_service import (
    _campaign,
    _save,
    _worker_poll_seconds,
    process_one,
    process_validation,
)


def make_campaign() -> Campaign:
    return Campaign(
        id="c1",
        target=TargetInput(
            name="demo",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        state=CampaignState.ready,
    )


def test_worker_save_rejects_stale_campaign_snapshot(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    first, first_version = _campaign(store, campaign.id)
    stale, stale_version = _campaign(store, campaign.id)
    assert first_version == stale_version == 1

    first.state = CampaignState.running
    assert _save(store, first, first_version) == 2

    stale.state = CampaignState.failed
    with pytest.raises(CampaignConflictError):
        _save(store, stale, stale_version)

    current, version = _campaign(store, campaign.id)
    assert version == 2
    assert current.state == CampaignState.running


def test_worker_poll_interval_is_bounded(monkeypatch):
    for value in ("invalid", "0.1", "61"):
        monkeypatch.setenv("XBOW_WORKER_POLL_SECONDS", value)
        with pytest.raises(ValueError, match="XBOW_WORKER_POLL_SECONDS"):
            _worker_poll_seconds()

    monkeypatch.setenv("XBOW_WORKER_POLL_SECONDS", "0.2")
    assert _worker_poll_seconds() == 0.2

    monkeypatch.setenv("XBOW_WORKER_POLL_SECONDS", "60")
    assert _worker_poll_seconds() == 60.0



def test_validation_worker_rejects_resolved_finding_before_probe(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = make_campaign()
    campaign.state = CampaignState.validating
    campaign.findings = [
        Finding(
            id="f1",
            title="fixture",
            severity="low",
            asset="https://example.test",
            summary="fixture",
            status="confirmed",
            discovered_by="scanner",
        )
    ]
    store.save_campaign(campaign.model_dump(mode="json"))

    job = {
        "id": "job-validation-stale",
        "campaign_id": campaign.id,
        "payload": {"finding_id": "f1"},
    }

    with pytest.raises(ValidationPolicyError, match="stale validation job"):
        process_validation(job, store)


def test_validation_worker_rejects_completed_campaign_before_probe(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = make_campaign()
    campaign.state = CampaignState.completed
    campaign.findings = [
        Finding(
            id="f1",
            title="fixture",
            severity="low",
            asset="https://example.test",
            summary="fixture",
            status="validation_required",
            discovered_by="scanner",
        )
    ]
    store.save_campaign(campaign.model_dump(mode="json"))

    job = {
        "id": "job-validation-completed",
        "campaign_id": campaign.id,
        "payload": {"finding_id": "f1"},
    }

    with pytest.raises(ValidationPolicyError, match="completed campaign"):
        process_validation(job, store)



def test_stale_validation_job_is_cancelled_without_retry(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    campaign.state = CampaignState.validating
    campaign.findings = [
        Finding(
            id="f1",
            title="fixture",
            severity="low",
            asset="https://example.test",
            summary="fixture",
            status="confirmed",
            discovered_by="scanner",
        )
    ]
    store.save_campaign(campaign.model_dump(mode="json"))
    job = queue.enqueue(
        campaign.id,
        "independent_validation",
        {
            "campaign_id": campaign.id,
            "finding_id": "f1",
            "asset": "https://example.test",
        },
        max_attempts=2,
        dedupe_key="validation:f1",
    )

    assert process_one(queue, store, "worker-stale") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "cancelled"
    assert final["attempts"] == 1
    assert final["claimed_by"] is None
    assert queue.claim("worker-retry") is None


def test_completed_campaign_validation_job_is_cancelled_without_retry(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    campaign.state = CampaignState.completed
    campaign.findings = [
        Finding(
            id="f1",
            title="fixture",
            severity="low",
            asset="https://example.test",
            summary="fixture",
            status="validation_required",
            discovered_by="scanner",
        )
    ]
    store.save_campaign(campaign.model_dump(mode="json"))
    job = queue.enqueue(
        campaign.id,
        "independent_validation",
        {
            "campaign_id": campaign.id,
            "finding_id": "f1",
            "asset": "https://example.test",
        },
        max_attempts=2,
        dedupe_key="validation:f1",
    )

    assert process_one(queue, store, "worker-completed") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "cancelled"
    assert final["attempts"] == 1
    assert queue.claim("worker-retry") is None
