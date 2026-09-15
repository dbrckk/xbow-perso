import pytest

from app.job_provenance import attach_job_provenance
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
        attach_job_provenance(
            {
                "campaign_id": campaign.id,
                "finding_id": "f1",
                "asset": "https://example.test",
            },
            campaign,
            job_kind="independent_validation",
            action="validate",
        ),
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
        attach_job_provenance(
            {
                "campaign_id": campaign.id,
                "finding_id": "f1",
                "asset": "https://example.test",
            },
            campaign,
            job_kind="independent_validation",
            action="validate",
        ),
        max_attempts=2,
        dedupe_key="validation:f1",
    )

    assert process_one(queue, store, "worker-completed") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "cancelled"
    assert final["attempts"] == 1
    assert queue.claim("worker-retry") is None



def test_completed_campaign_browser_job_is_cancelled_without_retry(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    campaign.state = CampaignState.completed
    store.save_campaign(campaign.model_dump(mode="json"))
    job = queue.enqueue(
        campaign.id,
        "browser_flow",
        attach_job_provenance(
            {
                "campaign_id": campaign.id,
                "steps": [
                    {
                        "operation": "navigate",
                        "url": "https://example.test",
                        "selector": None,
                        "secret_env": None,
                        "timeout_ms": 1000,
                    }
                ],
            },
            campaign,
            job_kind="browser_flow",
            action="crawl",
        ),
        max_attempts=2,
        dedupe_key="browser:stale-completed",
    )

    assert process_one(queue, store, "worker-browser-completed") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "cancelled"
    assert final["attempts"] == 1
    assert final["claimed_by"] is None
    assert queue.claim("worker-browser-retry") is None



def test_worker_rejects_policy_bound_job_after_scope_policy_changes(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    payload = attach_job_provenance(
        {"campaign_id": campaign.id, "platform": "generic"},
        campaign,
        job_kind="report",
        action="report",
    )
    job = queue.enqueue(
        campaign.id,
        "report",
        payload,
        max_attempts=1,
        dedupe_key="report:stale-policy",
    )

    document, version = store.get_campaign_record(campaign.id)
    document["target"]["rules"]["max_requests_per_second"] = 1.0
    store.save_campaign(document, expected_version=version)

    assert process_one(queue, store, "worker-policy-check") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "failed"
    assert final["attempts"] == 1
    assert "policy_fingerprint_mismatch" in str(final["last_error"])



def test_worker_rejects_unprovenanced_governed_job_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", raising=False)
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    job = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=1,
        dedupe_key="report:unprovenanced",
    )

    assert process_one(queue, store, "worker-strict-provenance") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "failed"
    assert final["attempts"] == 1
    assert "provenance_missing" in str(final["last_error"])


def test_legacy_unprovenanced_job_requires_explicit_compatibility_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", "true")
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    job = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=1,
        dedupe_key="report:legacy-compatible",
    )

    assert process_one(queue, store, "worker-legacy-provenance") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "completed"



def test_report_worker_persists_governance_fingerprints(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    job = queue.enqueue(
        campaign.id,
        "report",
        attach_job_provenance(
            {
                "campaign_id": campaign.id,
                "platform": "generic",
            },
            campaign,
            job_kind="report",
            action="report",
        ),
        max_attempts=1,
        dedupe_key="report:governance-manifest",
    )

    assert process_one(queue, store, "worker-report-governance") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "completed"

    reports = [
        item
        for item in store.list_artifacts(campaign.id)
        if item.get("kind") == "report"
    ]
    assert len(reports) == 1
    saved = store.get_campaign(campaign.id)
    report_event = next(
        event
        for event in saved["events"]
        if event.get("type") == "report_generated"
        and event.get("artifact_id") == reports[0]["id"]
    )
    assert len(report_event["reporting_governance_fingerprint"]) == 64
    assert len(report_event["report_provenance_fingerprint"]) == 64

    observations = store.list_observations(campaign.id)
    report_observation = next(
        item
        for item in observations
        if item.get("artifact_id") == reports[0]["id"]
        or (
            item.get("metadata", {}).get("artifact_kind") == "report"
            and item.get("metadata", {}).get(
                "reporting_governance_fingerprint"
            )
            == report_event["reporting_governance_fingerprint"]
        )
    )
    metadata = report_observation.get("metadata") or {}
    assert metadata["reporting_governance_verified"] is True

    _artifact, content = store.read_artifact(
        campaign.id,
        reports[0]["id"],
    )
    rendered = content.decode("utf-8")
    assert "## Governance & audit manifest" in rendered
    assert report_event["reporting_governance_fingerprint"] in rendered
