import pytest
from fastapi import HTTPException

from app import main
from app.jobqueue import JobQueue
from app.main import Campaign, CampaignState, ProgramRules, TargetInput


def _campaign():
    return Campaign(
        id="api-pentagi",
        state=CampaignState.ready,
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
                max_requests_per_second=1.0,
            ),
        ),
    )


def _configure(monkeypatch):
    monkeypatch.setenv("XBOW_PENTAGI_BASE_URL", "https://pentagi.example.test")
    monkeypatch.setenv("XBOW_PENTAGI_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", "2.0")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")


def test_pentagi_preview_exposes_metadata_not_request_payload(monkeypatch):
    _configure(monkeypatch)
    campaign = _campaign()
    monkeypatch.setattr(main, "assert_campaign_exists", lambda campaign_id: campaign)

    result = main.preview_pentagi_campaign(campaign.id)

    assert result["ready"] is True
    assert result["request_payload_exposed"] is False
    assert result["plan"]["target"] == str(campaign.target.primary_url)
    assert result["plan"]["endpoint"] == "https://pentagi.example.test/api/v1/graphql"
    assert result["plan"]["model_provider"] == "openai"
    assert "payload" not in result["plan"]


def test_pentagi_dispatch_enqueues_single_attempt_job_and_audits(tmp_path, monkeypatch):
    _configure(monkeypatch)
    campaign = _campaign()
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
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
        lambda value, expected_version=None: saved.append((value, expected_version)) or 8,
    )

    result = main.dispatch_pentagi_campaign(campaign.id)

    job = result["job"]
    persisted = jobs.get(job["id"])
    assert persisted is not None
    assert persisted["kind"] == "pentagi_flow"
    assert persisted["max_attempts"] == 1
    assert persisted["attempts"] == 0
    assert persisted["status"] == "queued"
    assert campaign.state == main.CampaignState.running
    assert saved and saved[0][1] == 7
    assert any(
        event.get("type") == "pentagi_flow_queued"
        and event.get("job_id") == job["id"]
        for event in campaign.events
    )

    repeated = main.dispatch_pentagi_campaign(campaign.id)
    assert repeated["job"]["id"] == job["id"]
    assert jobs.campaign_job_counts(campaign.id)["pentagi_flow"] == 1
    assert sum(
        1
        for event in campaign.events
        if event.get("type") == "pentagi_flow_queued"
        and event.get("job_id") == job["id"]
    ) == 1


def test_pentagi_dispatch_fails_closed_when_transport_disabled(tmp_path, monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "false")
    campaign = _campaign()
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))

    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 1),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)

    with pytest.raises(HTTPException) as exc:
        main.dispatch_pentagi_campaign(campaign.id)

    assert exc.value.status_code == 409
    assert "pentagi_transport_disabled" in str(exc.value.detail)
    assert jobs.stats()["total"] == 0


class _ArtifactStore:
    def list_artifacts(self, campaign_id):
        return [
            {"id": "a1", "kind": "pentagi_receipt"},
            {"id": "a2", "kind": "pentagi_status"},
            {"id": "a3", "kind": "report"},
        ]


def test_pentagi_status_summary_filters_local_artifacts(tmp_path, monkeypatch):
    campaign = _campaign()
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
    jobs.enqueue(
        campaign.id,
        "pentagi_flow",
        {"fixture": True},
        max_attempts=1,
        dedupe_key="flow-1",
    )
    jobs.enqueue(
        campaign.id,
        "pentagi_status",
        {"receipt_artifact_id": "a1"},
        max_attempts=3,
        dedupe_key="status-1",
    )

    monkeypatch.setattr(main, "assert_campaign_exists", lambda campaign_id: campaign)
    monkeypatch.setattr(main, "queue", lambda: jobs)
    monkeypatch.setattr(main, "storage", lambda: _ArtifactStore())

    result = main.pentagi_campaign_status(campaign.id)

    assert result["jobs"] == {"pentagi_flow": 1, "pentagi_status": 1}
    assert [item["kind"] for item in result["artifacts"]] == [
        "pentagi_receipt",
        "pentagi_status",
    ]
    assert result["read_only"] is True


def test_pentagi_dispatch_rejects_closed_lifecycle(tmp_path, monkeypatch):
    _configure(monkeypatch)
    campaign = _campaign()
    campaign.state = main.CampaignState.completed
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 3),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)

    with pytest.raises(HTTPException) as exc:
        main.dispatch_pentagi_campaign(campaign.id)

    assert exc.value.status_code == 409
    assert "Cannot dispatch PentAGI from completed" in str(exc.value.detail)
    assert jobs.stats()["total"] == 0
