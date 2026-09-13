import pytest
from fastapi import HTTPException

from app import main
from app.campaign_audit import append_campaign_event
from app.jobqueue import JobQueue
from app.main import (
    Campaign,
    CampaignState,
    EvidenceInput,
    Finding,
    ProgramRules,
    TargetInput,
    add_finding,
    add_text_artifact,
    queue_report,
    start_campaign,
    validate_finding,
)
from app.observation_graph import Observation
from app.storage import Storage


def _setup(tmp_path, monkeypatch, *, findings=None):
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
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=findings or [],
    )
    Storage(db, artifacts).save_campaign(campaign.model_dump(mode="json"))
    return db, artifacts


def _record_observed_validation(db, artifacts, finding_id="f1"):
    store = Storage(db, artifacts)
    store.put_observation("c1", Observation("a1", "asset", "example.test", "scanner").to_dict())
    store.put_observation(
        "c1",
        Observation(
            f"finding:{finding_id}",
            "finding",
            finding_id,
            "scanner",
            parent_ids=("a1",),
        ).to_dict(),
    )
    store.put_observation(
        "c1",
        Observation(
            "v1",
            "validation",
            "observed",
            "independent-http-validator",
            parent_ids=(f"finding:{finding_id}",),
        ).to_dict(),
    )


def test_duplicate_finding_retry_returns_existing_and_keeps_one_job(tmp_path, monkeypatch):
    db, _ = _setup(tmp_path, monkeypatch)
    finding = Finding(
        id="f1",
        title="candidate",
        severity="medium",
        asset="https://example.test/path",
        summary="bounded fixture",
        discovered_by="fixture",
    )

    first = add_finding("c1", finding.model_copy(deep=True))
    second = add_finding("c1", finding.model_copy(deep=True))

    assert first.id == second.id == "f1"
    stored = Storage(db).get_campaign("c1")
    assert len(stored["findings"]) == 1
    assert JobQueue(db).stats()["total"] == 1


def test_resolution_requires_observed_independent_validation(tmp_path, monkeypatch):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    db, _ = _setup(tmp_path, monkeypatch, findings=[finding])

    with pytest.raises(HTTPException) as exc:
        validate_finding("c1", "f1", True, "human-reviewer")

    assert exc.value.status_code == 409
    stored = Storage(db).get_campaign("c1")
    assert stored["findings"][0]["status"] == "validation_required"
    assert JobQueue(db).stats()["total"] == 0


def test_repeated_validation_does_not_queue_duplicate_report(tmp_path, monkeypatch):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    db, artifacts = _setup(tmp_path, monkeypatch, findings=[finding])
    _record_observed_validation(db, artifacts)

    first = validate_finding("c1", "f1", True, "human-reviewer")
    second = validate_finding("c1", "f1", True, "human-reviewer")

    assert first.status == second.status == "confirmed"
    assert JobQueue(db).stats()["total"] == 1


def test_self_sourced_observation_cannot_unlock_resolution(tmp_path, monkeypatch):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    db, artifacts = _setup(tmp_path, monkeypatch, findings=[finding])
    store = Storage(db, artifacts)
    store.put_observation("c1", Observation("a1", "asset", "example.test", "scanner").to_dict())
    store.put_observation(
        "c1",
        Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)).to_dict(),
    )
    store.put_observation(
        "c1",
        Observation("v1", "validation", "observed", "scanner", parent_ids=("finding:f1",)).to_dict(),
    )

    with pytest.raises(HTTPException) as exc:
        validate_finding("c1", "f1", False, "human-reviewer")

    assert exc.value.status_code == 409
    assert Storage(db).get_campaign("c1")["findings"][0]["status"] == "validation_required"


def test_duplicate_text_artifact_retry_reuses_artifact_and_event(tmp_path, monkeypatch):
    db, artifacts = _setup(tmp_path, monkeypatch)
    evidence = EvidenceInput(kind="http_evidence", content="same evidence", media_type="text/plain")

    first = add_text_artifact("c1", evidence)
    second = add_text_artifact("c1", evidence)

    assert first["id"] == second["id"]
    store = Storage(db, artifacts)
    assert len(store.list_artifacts("c1")) == 1
    campaign = store.get_campaign("c1")
    events = [event for event in campaign["events"] if event.get("type") == "artifact_stored"]
    assert len(events) == 1


def test_completed_campaign_rejects_new_findings(tmp_path, monkeypatch):
    db, artifacts = _setup(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    document, version = store.get_campaign_record("c1")
    document["state"] = "completed"
    store.save_campaign(document, expected_version=version)

    candidate = Finding(
        id="f-new",
        title="new candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        discovered_by="scanner",
    )

    with pytest.raises(HTTPException) as exc:
        add_finding("c1", candidate)

    assert exc.value.status_code == 409
    assert "completed" in str(exc.value.detail)
    assert Storage(db).get_campaign("c1")["findings"] == []
    assert JobQueue(db).stats()["total"] == 0


def test_campaign_start_conflict_before_intent_commit_never_enqueues(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "queue.sqlite3")
    campaign = Campaign(
        id="start-conflict",
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
    jobs = JobQueue(db)

    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 4),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)
    monkeypatch.setattr(
        main,
        "save_campaign",
        lambda value, expected_version=None: (_ for _ in ()).throw(
            HTTPException(
                status_code=409,
                detail="Campaign changed concurrently; reload and retry",
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        start_campaign(campaign.id)

    assert exc.value.status_code == 409
    assert jobs.stats()["total"] == 0
    assert any(
        event.get("type") == "campaign_start_requested"
        for event in campaign.events
    )
    assert not any(
        event.get("type") == "campaign_started"
        for event in campaign.events
    )


def test_campaign_start_retry_after_enqueue_reuses_pending_request(
    tmp_path,
    monkeypatch,
):
    db, artifacts = _setup(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    document, version = store.get_campaign_record("c1")
    campaign = Campaign.model_validate(document)
    campaign.state = CampaignState.ready
    request_id = "resume-start-request"
    receipt = main.policy_receipt(
        campaign,
        "example.test",
        "automated_scan",
    )
    append_campaign_event(
        campaign.events,
        {
            "type": "campaign_start_requested",
            "request_id": request_id,
            "at": main.utcnow(),
            "policy": receipt,
        },
    )
    campaign.updated_at = main.utcnow()
    store.save_campaign(
        campaign.model_dump(mode="json"),
        expected_version=version,
    )

    jobs = JobQueue(db)
    payload = main.sanitized_scan_payload(campaign, receipt)
    existing = jobs.enqueue(
        campaign.id,
        "strix_scan",
        payload,
        max_attempts=2,
        dedupe_key=f"api:start:{request_id}",
    )

    result = start_campaign(campaign.id)

    assert result["request_id"] == request_id
    assert result["job"]["id"] == existing["id"]
    assert result["audit_reconciled"] is True
    assert jobs.stats()["total"] == 1

    persisted = store.get_campaign(campaign.id)
    assert persisted["state"] == "running"
    requested = [
        event
        for event in persisted["events"]
        if event.get("type") == "campaign_start_requested"
        and event.get("request_id") == request_id
    ]
    started = [
        event
        for event in persisted["events"]
        if event.get("type") == "campaign_started"
        and event.get("request_id") == request_id
    ]
    assert len(requested) == 1
    assert len(started) == 1
    assert started[0]["job_id"] == existing["id"]



def test_campaign_start_reconciliation_never_reopens_completed_campaign(monkeypatch):
    campaign = Campaign(
        id="completed-start",
        state=CampaignState.completed,
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign.model_copy(deep=True), 7),
    )

    with pytest.raises(HTTPException) as exc:
        main._reconcile_campaign_started(
            campaign.id,
            {"id": "job-1"},
            request_id="request-1",
            receipt={"allowed": True},
        )

    assert exc.value.status_code == 409
    assert "completed" in str(exc.value.detail)
    assert campaign.state == CampaignState.completed



def test_add_finding_conflict_before_validation_intent_commit_never_enqueues(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "queue.sqlite3")
    campaign = Campaign(
        id="finding-conflict",
        state=CampaignState.running,
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    jobs = JobQueue(db)
    finding = Finding(
        id="f-conflict",
        title="candidate",
        severity="medium",
        asset="https://example.test/path",
        summary="fixture",
        discovered_by="fixture",
    )

    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 5),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)
    monkeypatch.setattr(
        main,
        "save_campaign",
        lambda value, expected_version=None: (_ for _ in ()).throw(
            HTTPException(
                status_code=409,
                detail="Campaign changed concurrently; reload and retry",
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        add_finding(campaign.id, finding)

    assert exc.value.status_code == 409
    assert jobs.stats()["total"] == 0
    assert any(
        event.get("type") == "validation_requested"
        and event.get("finding_id") == finding.id
        for event in campaign.events
    )
    assert not any(
        event.get("type") == "validation_queued"
        for event in campaign.events
    )


def test_add_finding_retry_repairs_missing_validation_job_after_intent(
    tmp_path,
    monkeypatch,
):
    db, artifacts = _setup(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    document, version = store.get_campaign_record("c1")
    campaign = Campaign.model_validate(document)
    finding = Finding(
        id="f-resume",
        title="candidate",
        severity="medium",
        asset="https://example.test/resume",
        summary="fixture",
        discovered_by="fixture",
        status="validation_required",
    )
    campaign.findings.append(finding)
    campaign.state = CampaignState.validating
    append_campaign_event(
        campaign.events,
        {
            "type": "finding_received",
            "finding_id": finding.id,
            "at": main.utcnow(),
        },
    )
    append_campaign_event(
        campaign.events,
        {
            "type": "validation_requested",
            "finding_id": finding.id,
            "request_id": f"validation:{finding.id}",
            "at": main.utcnow(),
        },
    )
    campaign.updated_at = main.utcnow()
    store.save_campaign(
        campaign.model_dump(mode="json"),
        expected_version=version,
    )

    result = add_finding(
        campaign.id,
        Finding(
            id=finding.id,
            title=finding.title,
            severity=finding.severity,
            asset=finding.asset,
            summary=finding.summary,
            discovered_by=finding.discovered_by,
        ),
    )

    assert result.id == finding.id
    jobs = JobQueue(db)
    assert jobs.campaign_job_counts(campaign.id)["independent_validation"] == 1
    persisted = store.get_campaign(campaign.id)
    queued = [
        event
        for event in persisted["events"]
        if event.get("type") == "validation_queued"
        and event.get("finding_id") == finding.id
    ]
    assert len(queued) == 1
    assert queued[0]["request_id"] == f"validation:{finding.id}"



def test_manual_report_conflict_before_intent_commit_never_enqueues(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "queue.sqlite3")
    campaign = Campaign(
        id="report-conflict",
        state=CampaignState.running,
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    jobs = JobQueue(db)

    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 3),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)
    monkeypatch.setattr(
        main,
        "save_campaign",
        lambda value, expected_version=None: (_ for _ in ()).throw(
            HTTPException(
                status_code=409,
                detail="Campaign changed concurrently; reload and retry",
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        queue_report(campaign.id, "generic")

    assert exc.value.status_code == 409
    assert jobs.stats()["total"] == 0
    assert any(
        event.get("type") == "report_requested"
        and event.get("purpose") == "manual"
        for event in campaign.events
    )
    assert not any(
        event.get("type") == "report_queued"
        for event in campaign.events
    )


def test_manual_report_retry_reuses_pending_request_and_job(tmp_path, monkeypatch):
    db, artifacts = _setup(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    document, version = store.get_campaign_record("c1")
    campaign = Campaign.model_validate(document)
    request_id = "manual-report-resume"
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
    campaign.updated_at = main.utcnow()
    store.save_campaign(
        campaign.model_dump(mode="json"),
        expected_version=version,
    )

    jobs = JobQueue(db)
    existing = jobs.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=2,
        dedupe_key=f"report:generic:{request_id}",
    )

    result = queue_report(campaign.id, "generic")

    assert result["id"] == existing["id"]
    assert jobs.campaign_job_counts(campaign.id)["report"] == 1
    persisted = store.get_campaign(campaign.id)
    queued = [
        event
        for event in persisted["events"]
        if event.get("type") == "report_queued"
        and event.get("request_id") == request_id
    ]
    assert len(queued) == 1
    assert queued[0]["job_id"] == existing["id"]


def test_final_validation_conflict_before_completion_intent_never_enqueues_report(
    tmp_path,
    monkeypatch,
):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    db, artifacts = _setup(tmp_path, monkeypatch, findings=[finding])
    _record_observed_validation(db, artifacts)
    jobs = JobQueue(db)
    original_save = main.save_campaign

    def fail_save(value, expected_version=None):
        raise HTTPException(
            status_code=409,
            detail="Campaign changed concurrently; reload and retry",
        )

    monkeypatch.setattr(main, "save_campaign", fail_save)
    monkeypatch.setattr(main, "queue", lambda: jobs)

    with pytest.raises(HTTPException) as exc:
        validate_finding("c1", "f1", True, "human-reviewer")

    assert exc.value.status_code == 409
    assert jobs.campaign_job_counts("c1")["report"] == 0

    monkeypatch.setattr(main, "save_campaign", original_save)
