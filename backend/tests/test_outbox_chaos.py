from __future__ import annotations

from app import main
from app.campaign_audit import append_campaign_event
from app.jobqueue import JobQueue
from app.main import Campaign, CampaignState, ProgramRules, TargetInput
from app.storage import Storage


def _campaign() -> Campaign:
    return Campaign(
        id="chaos-campaign",
        state=CampaignState.ready,
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )


def _configure(tmp_path, monkeypatch):
    db = str(tmp_path / "xbow.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    return db, artifacts


def test_restart_after_start_intent_resumes_with_single_job(tmp_path, monkeypatch):
    db, artifacts = _configure(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    document, version = store.get_campaign_record(campaign.id)
    interrupted = Campaign.model_validate(document)
    request_id = "chaos-start-after-intent"
    receipt = main.policy_receipt(interrupted, "example.test", "automated_scan")
    append_campaign_event(
        interrupted.events,
        {
            "type": "campaign_start_requested",
            "request_id": request_id,
            "policy": receipt,
            "at": main.utcnow(),
        },
    )
    interrupted.updated_at = main.utcnow()
    store.save_campaign(interrupted.model_dump(mode="json"), expected_version=version)

    # Process restart: construct fresh storage/queue instances and retry the API.
    restarted_queue = JobQueue(db)
    assert restarted_queue.stats()["total"] == 0

    result = main.start_campaign(campaign.id)

    assert result["request_id"] == request_id
    assert JobQueue(db).stats()["total"] == 1
    persisted = Storage(db, artifacts).get_campaign(campaign.id)
    assert persisted["state"] == "running"
    assert len(
        [
            event
            for event in persisted["events"]
            if event.get("type") == "campaign_start_requested"
            and event.get("request_id") == request_id
        ]
    ) == 1
    assert len(
        [
            event
            for event in persisted["events"]
            if event.get("type") == "campaign_started"
            and event.get("request_id") == request_id
        ]
    ) == 1


def test_restart_after_enqueue_reuses_same_start_job(tmp_path, monkeypatch):
    db, artifacts = _configure(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    document, version = store.get_campaign_record(campaign.id)
    interrupted = Campaign.model_validate(document)
    request_id = "chaos-start-after-enqueue"
    receipt = main.policy_receipt(interrupted, "example.test", "automated_scan")
    append_campaign_event(
        interrupted.events,
        {
            "type": "campaign_start_requested",
            "request_id": request_id,
            "policy": receipt,
            "at": main.utcnow(),
        },
    )
    interrupted.updated_at = main.utcnow()
    store.save_campaign(interrupted.model_dump(mode="json"), expected_version=version)

    payload = main.sanitized_scan_payload(interrupted, receipt)
    before_restart = JobQueue(db)
    existing = before_restart.enqueue(
        campaign.id,
        "strix_scan",
        payload,
        max_attempts=2,
        dedupe_key=f"api:start:{request_id}",
    )
    assert before_restart.stats()["total"] == 1

    # Simulate losing all process memory after enqueue but before audit reconciliation.
    after_restart = JobQueue(db)
    recovered = after_restart.get_by_dedupe(
        campaign.id,
        "strix_scan",
        f"api:start:{request_id}",
    )
    assert recovered is not None and recovered["id"] == existing["id"]

    result = main.start_campaign(campaign.id)

    assert result["job"]["id"] == existing["id"]
    assert JobQueue(db).stats()["total"] == 1
    persisted = Storage(db, artifacts).get_campaign(campaign.id)
    started = [
        event
        for event in persisted["events"]
        if event.get("type") == "campaign_started"
        and event.get("request_id") == request_id
    ]
    assert len(started) == 1
    assert started[0]["job_id"] == existing["id"]


def test_restart_after_manual_report_enqueue_is_repaired_locally(tmp_path, monkeypatch):
    db, artifacts = _configure(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    campaign = _campaign()
    campaign.state = CampaignState.running
    request_id = "chaos-report-after-enqueue"
    append_campaign_event(
        campaign.events,
        {
            "type": "report_requested",
            "request_id": request_id,
            "platform": "generic",
            "purpose": "manual",
            "at": main.utcnow(),
        },
    )
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    queue_before = JobQueue(db)
    existing = queue_before.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=2,
        dedupe_key=f"report:generic:{request_id}",
    )

    # Restart before report_queued audit event is saved.
    queue_after = JobQueue(db)
    assert (
        queue_after.get_by_dedupe(
            campaign.id,
            "report",
            f"report:generic:{request_id}",
        )["id"]
        == existing["id"]
    )

    result = main.reconcile_campaign_outbox_local(campaign.id)

    assert result["repaired"] == 1
    assert result["remaining"] == []
    assert JobQueue(db).stats()["total"] == 1
    persisted = Storage(db, artifacts).get_campaign(campaign.id)
    events = [
        event
        for event in persisted["events"]
        if event.get("type") == "report_queued"
        and event.get("request_id") == request_id
    ]
    assert len(events) == 1
    assert events[0]["job_id"] == existing["id"]
    assert events[0]["reconciled_locally"] is True


def test_restart_with_missing_job_never_recreates_work(tmp_path, monkeypatch):
    db, artifacts = _configure(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    campaign = _campaign()
    campaign.state = CampaignState.validating
    append_campaign_event(
        campaign.events,
        {
            "type": "validation_requested",
            "request_id": "validation:missing-chaos",
            "finding_id": "missing-chaos",
            "at": main.utcnow(),
        },
    )
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    # Restart with no corresponding queue row at all.
    assert JobQueue(db).stats()["total"] == 0

    result = main.reconcile_campaign_outbox_local(campaign.id)

    assert result["repaired"] == 0
    assert result["remaining"][0]["diagnosis"] == "job_missing"
    assert result["automatic_job_creation"] is False
    assert JobQueue(db).stats()["total"] == 0


def test_queue_restart_preserves_dedupe_identity_and_terminal_status(tmp_path):
    db = str(tmp_path / "queue.sqlite3")
    first = JobQueue(db)
    job = first.enqueue(
        "campaign-restart",
        "report",
        {"campaign_id": "campaign-restart", "platform": "generic"},
        max_attempts=1,
        dedupe_key="report:generic:restart",
    )
    claimed = first.claim("worker-before-restart")
    assert claimed is not None and claimed["id"] == job["id"]
    failed = first.finish(
        job["id"],
        "worker-before-restart",
        False,
        "terminal fixture",
    )
    assert failed is not None and failed["status"] == "failed"

    restarted = JobQueue(db)
    recovered = restarted.get_by_dedupe(
        "campaign-restart",
        "report",
        "report:generic:restart",
    )

    assert recovered is not None
    assert recovered["id"] == job["id"]
    assert recovered["status"] == "failed"
    assert restarted.stats()["total"] == 1
