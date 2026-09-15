from app import worker_service
from app.job_provenance import attach_job_provenance
from app.jobqueue import JobQueue
from app.main import Campaign, CampaignState, ProgramRules, TargetInput
from app.storage import Storage


def _runtime(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = Campaign(
        id="worker-provenance",
        state=CampaignState.ready,
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="authorization-1",
                allowed_targets=["example.test"],
                max_requests_per_second=2.0,
            ),
        ),
    )
    store.save_campaign(campaign.model_dump(mode="json"))
    return campaign, store, queue


def _stub_execution(monkeypatch):
    monkeypatch.setattr(worker_service, "process_report", lambda job, store: None)
    monkeypatch.setattr(
        worker_service,
        "advance_campaign",
        lambda campaign, queue, store: {"action": {"kind": "stop"}},
    )


def test_worker_rejects_governed_job_when_policy_fingerprint_is_stale(tmp_path, monkeypatch):
    campaign, store, queue = _runtime(tmp_path)
    _stub_execution(monkeypatch)
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
        dedupe_key="stale-policy",
    )

    raw, version = store.get_campaign_record(campaign.id)
    current = Campaign.model_validate(raw)
    current.target.rules.max_requests_per_second = 3.0
    store.save_campaign(current.model_dump(mode="json"), expected_version=version)

    assert worker_service.process_one(queue, store, "worker-stale-policy") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "failed"
    assert "policy_fingerprint_mismatch" in (final["last_error"] or "")


def test_worker_rejects_unprovenanced_governed_job_by_default(tmp_path, monkeypatch):
    campaign, store, queue = _runtime(tmp_path)
    _stub_execution(monkeypatch)
    monkeypatch.delenv("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", raising=False)
    job = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=1,
        dedupe_key="missing-provenance",
    )

    assert worker_service.process_one(queue, store, "worker-missing-provenance") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "failed"
    assert "provenance_missing" in (final["last_error"] or "")


def test_worker_legacy_flag_allows_unprovenanced_governed_job(tmp_path, monkeypatch):
    campaign, store, queue = _runtime(tmp_path)
    _stub_execution(monkeypatch)
    monkeypatch.setenv("XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS", "true")
    job = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=1,
        dedupe_key="legacy-provenance",
    )

    assert worker_service.process_one(queue, store, "worker-legacy") is True

    final = queue.get(job["id"])
    assert final is not None
    assert final["status"] == "completed"
    assert final["last_error"] is None
