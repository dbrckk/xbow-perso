import pytest

from app import main
from app.api_outbox import outbox_snapshot
from app.jobqueue import JobQueue
from app.main import Campaign, CampaignState, ProgramRules, TargetInput


def _campaign(events):
    return Campaign(
        id="outbox-campaign",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        events=events,
    )


def test_outbox_snapshot_reports_only_unresolved_intents_and_redacts_ids():
    events = [
        {
            "type": "campaign_start_requested",
            "request_id": "start-secret-id",
            "at": "2026-09-13T10:00:00+00:00",
        },
        {
            "type": "validation_requested",
            "request_id": "validation:f1",
            "finding_id": "f1",
            "at": "2026-09-13T10:01:00+00:00",
        },
        {
            "type": "validation_queued",
            "request_id": "validation:f1",
            "finding_id": "f1",
            "job_id": "job-validation",
            "at": "2026-09-13T10:01:10+00:00",
        },
        {
            "type": "report_requested",
            "request_id": "manual-report-secret",
            "platform": "generic",
            "purpose": "manual",
            "at": "2026-09-13T10:02:00+00:00",
        },
        {
            "type": "pentagi_dispatch_requested",
            "dispatch_fingerprint": "a" * 64,
            "at": "2026-09-13T10:03:00+00:00",
        },
        {
            "type": "pentagi_flow_queued",
            "dispatch_fingerprint": "a" * 64,
            "job_id": "pentagi-job",
            "at": "2026-09-13T10:03:10+00:00",
        },
    ]

    snapshot = outbox_snapshot(events)

    assert snapshot["pending_total"] == 2
    assert snapshot["pending_by_kind"] == {
        "campaign_start": 1,
        "report_manual": 1,
    }
    assert snapshot["oldest_pending_at"] == "2026-09-13T10:00:00+00:00"
    assert snapshot["identities_redacted"] is True
    assert snapshot["truncated"] is False
    rendered = str(snapshot)
    assert "start-secret-id" not in rendered
    assert "manual-report-secret" not in rendered
    assert "validation:f1" not in rendered
    assert "a" * 64 not in rendered


def test_outbox_snapshot_tracks_completion_report_separately():
    events = [
        {
            "type": "report_requested",
            "request_id": "report:generic:completed",
            "platform": "generic",
            "purpose": "campaign_completion",
            "at": "2026-09-13T10:00:00+00:00",
        }
    ]

    snapshot = outbox_snapshot(events)

    assert snapshot["pending_by_kind"] == {"campaign_completion_report": 1}

    events.append(
        {
            "type": "campaign_completed",
            "request_id": "report:generic:completed",
            "platform": "generic",
            "purpose": "campaign_completion",
            "job_id": "report-job",
            "at": "2026-09-13T10:01:00+00:00",
        }
    )
    assert outbox_snapshot(events)["pending_total"] == 0


def test_outbox_snapshot_bounds_visible_items():
    events = [
        {
            "type": "campaign_start_requested",
            "request_id": f"request-{index}",
            "at": f"2026-09-13T10:{index:02d}:00+00:00",
        }
        for index in range(3)
    ]

    snapshot = outbox_snapshot(events, max_items=2)

    assert snapshot["pending_total"] == 3
    assert len(snapshot["pending"]) == 2
    assert snapshot["truncated"] is True

    for invalid in (0, 501):
        with pytest.raises(ValueError, match="max_items"):
            outbox_snapshot(events, max_items=invalid)


def test_campaign_outbox_api_is_read_only_and_redacted(monkeypatch):
    campaign = _campaign(
        [
            {
                "type": "campaign_start_requested",
                "request_id": "api-secret-request",
                "at": "2026-09-13T10:00:00+00:00",
            }
        ]
    )
    monkeypatch.setattr(main, "assert_campaign_exists", lambda campaign_id: campaign)

    result = main.campaign_outbox_status(campaign.id, limit=10)

    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["pending_total"] == 1
    assert "api-secret-request" not in str(result)


def test_campaign_outbox_api_rejects_invalid_limit(monkeypatch):
    campaign = _campaign([])
    monkeypatch.setattr(main, "assert_campaign_exists", lambda campaign_id: campaign)

    with pytest.raises(main.HTTPException) as exc:
        main.campaign_outbox_status(campaign.id, limit=0)

    assert exc.value.status_code == 400



def test_outbox_recovery_reports_job_missing_without_creating_job(tmp_path, monkeypatch):
    campaign = _campaign(
        [
            {
                "type": "report_requested",
                "request_id": "missing-report-request",
                "platform": "generic",
                "purpose": "manual",
                "at": "2026-09-13T10:00:00+00:00",
            }
        ]
    )
    campaign.state = CampaignState.running
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
    monkeypatch.setattr(main, "assert_campaign_exists", lambda campaign_id: campaign)
    monkeypatch.setattr(main, "queue", lambda: jobs)

    result = main.campaign_outbox_recovery(campaign.id)

    assert jobs.stats()["total"] == 0
    assert result["automatic_job_creation"] is False
    assert result["diagnostics"][0]["diagnosis"] == "job_missing"
    assert result["diagnostics"][0]["repairable_local_audit"] is False
    assert "missing-report-request" not in str(result)


def test_outbox_recovery_reports_terminal_job_without_raw_ids(tmp_path, monkeypatch):
    campaign = _campaign(
        [
            {
                "type": "report_requested",
                "request_id": "terminal-report-request",
                "platform": "generic",
                "purpose": "manual",
                "at": "2026-09-13T10:00:00+00:00",
            }
        ]
    )
    campaign.state = CampaignState.running
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = jobs.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=1,
        dedupe_key="report:generic:terminal-report-request",
    )
    claimed = jobs.claim("worker-terminal")
    assert claimed is not None and claimed["id"] == job["id"]
    failed = jobs.finish(job["id"], "worker-terminal", False, "fixture failure")
    assert failed is not None and failed["status"] == "failed"

    monkeypatch.setattr(main, "assert_campaign_exists", lambda campaign_id: campaign)
    monkeypatch.setattr(main, "queue", lambda: jobs)

    result = main.campaign_outbox_recovery(campaign.id)

    diagnostic = result["diagnostics"][0]
    assert diagnostic["diagnosis"] == "job_terminal"
    assert diagnostic["job_status"] == "failed"
    assert diagnostic["repairable_local_audit"] is True
    assert "terminal-report-request" not in str(result)
    assert job["id"] not in str(result)


def test_local_reconcile_repairs_existing_report_audit_without_enqueue(
    tmp_path,
    monkeypatch,
):
    campaign = _campaign(
        [
            {
                "type": "report_requested",
                "request_id": "repair-report-request",
                "platform": "generic",
                "purpose": "manual",
                "at": "2026-09-13T10:00:00+00:00",
            }
        ]
    )
    campaign.state = CampaignState.running
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = jobs.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        dedupe_key="report:generic:repair-report-request",
    )
    saved = []

    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 7),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)
    monkeypatch.setattr(
        main,
        "save_campaign",
        lambda value, expected_version=None: saved.append(
            (value.model_copy(deep=True), expected_version)
        )
        or expected_version + 1,
    )

    result = main.reconcile_campaign_outbox_local(campaign.id)

    assert result["repaired"] == 1
    assert result["skipped_ambiguous"] == 0
    assert result["remaining"] == []
    assert result["automatic_job_creation"] is False
    assert jobs.stats()["total"] == 1
    repaired = [
        event
        for event in campaign.events
        if event.get("type") == "report_queued"
        and event.get("request_id") == "repair-report-request"
    ]
    assert len(repaired) == 1
    assert repaired[0]["job_id"] == job["id"]
    assert repaired[0]["reconciled_locally"] is True
    assert saved and saved[0][1] == 7


def test_local_reconcile_never_creates_missing_job(tmp_path, monkeypatch):
    campaign = _campaign(
        [
            {
                "type": "validation_requested",
                "request_id": "validation:f-missing",
                "finding_id": "f-missing",
                "at": "2026-09-13T10:00:00+00:00",
            }
        ]
    )
    campaign.state = CampaignState.validating
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
    saved = []

    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 2),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)
    monkeypatch.setattr(
        main,
        "save_campaign",
        lambda value, expected_version=None: saved.append(value) or 3,
    )

    result = main.reconcile_campaign_outbox_local(campaign.id)

    assert result["repaired"] == 0
    assert jobs.stats()["total"] == 0
    assert saved == []
    assert result["remaining"][0]["diagnosis"] == "job_missing"


def test_local_reconcile_skips_ambiguous_completed_start_job(tmp_path, monkeypatch):
    campaign = _campaign(
        [
            {
                "type": "campaign_start_requested",
                "request_id": "ambiguous-start-request",
                "policy": {"allowed": True},
                "at": "2026-09-13T10:00:00+00:00",
            }
        ]
    )
    campaign.state = CampaignState.ready
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = jobs.enqueue(
        campaign.id,
        "strix_scan",
        {"campaign_id": campaign.id},
        max_attempts=1,
        dedupe_key="api:start:ambiguous-start-request",
    )
    claimed = jobs.claim("worker-start")
    assert claimed is not None and claimed["id"] == job["id"]
    completed = jobs.finish(job["id"], "worker-start", True)
    assert completed is not None and completed["status"] == "completed"
    saved = []

    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 4),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)
    monkeypatch.setattr(
        main,
        "save_campaign",
        lambda value, expected_version=None: saved.append(value) or 5,
    )

    result = main.reconcile_campaign_outbox_local(campaign.id)

    assert result["repaired"] == 0
    assert result["skipped_ambiguous"] == 1
    assert saved == []
    assert result["remaining"][0]["diagnosis"] == "audit_missing"
