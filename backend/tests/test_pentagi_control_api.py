from dataclasses import replace

import pytest
from fastapi import HTTPException

from app import main, pentagi_control
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

    assert result["ready"] is False
    assert result["request_payload_exposed"] is False
    assert result["plan"]["target"] == str(campaign.target.primary_url)
    assert result["plan"]["model_provider"] == "openai"
    assert result["plan"]["execution_supported"] is False
    assert "execution_transport_not_enforceable" in result["admission"]["reasons"]
    assert "endpoint" not in result["plan"]
    assert "payload" not in result["plan"]


def test_pentagi_dispatch_is_fail_closed_without_enforcing_transport(tmp_path, monkeypatch):
    _configure(monkeypatch)
    campaign = _campaign()
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))

    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 7),
    )
    monkeypatch.setattr(main, "queue", lambda: jobs)

    with pytest.raises(HTTPException) as exc:
        main.dispatch_pentagi_campaign(campaign.id)

    assert exc.value.status_code == 409
    assert "execution_transport_not_enforceable" in str(exc.value.detail)
    assert jobs.stats()["total"] == 0


def test_pentagi_dispatch_conflict_before_intent_persistence_never_enqueues(
    tmp_path,
    monkeypatch,
):
    _configure(monkeypatch)
    campaign = _campaign()
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))

    preview = pentagi_control.prepare_pentagi_control_preview(campaign)
    executable_plan = replace(
        preview.plan,
        dry_run=False,
        execution_supported=True,
    )
    executable_decision = pentagi_control.evaluate_pentagi_admission(
        campaign,
        executable_plan,
    )
    future_preview = pentagi_control.PentagiControlPreview(
        plan=executable_plan,
        decision=executable_decision,
        operational_reasons=(),
    )

    monkeypatch.setattr(
        pentagi_control,
        "require_pentagi_control_ready",
        lambda value: future_preview,
    )
    monkeypatch.setattr(
        main,
        "assert_campaign_record",
        lambda campaign_id: (campaign, 7),
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
        main.dispatch_pentagi_campaign(campaign.id)

    assert exc.value.status_code == 409
    assert jobs.stats()["total"] == 0
    assert any(
        event.get("type") == "pentagi_dispatch_requested"
        for event in campaign.events
    )
    assert not any(
        event.get("type") == "pentagi_flow_queued"
        for event in campaign.events
    )


def test_future_enforceable_dispatch_response_is_sanitized_and_idempotent(
    tmp_path,
    monkeypatch,
):
    _configure(monkeypatch)
    campaign = _campaign()
    jobs = JobQueue(str(tmp_path / "queue.sqlite3"))
    saved = []

    preview = pentagi_control.prepare_pentagi_control_preview(campaign)
    executable_plan = replace(
        preview.plan,
        dry_run=False,
        execution_supported=True,
    )
    executable_decision = pentagi_control.evaluate_pentagi_admission(
        campaign,
        executable_plan,
    )
    future_preview = pentagi_control.PentagiControlPreview(
        plan=executable_plan,
        decision=executable_decision,
        operational_reasons=(),
    )
    assert future_preview.decision.allowed is True

    monkeypatch.setattr(
        pentagi_control,
        "require_pentagi_control_ready",
        lambda value: future_preview,
    )
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

    safe_job = result["job"]
    assert set(safe_job) == {
        "id",
        "kind",
        "status",
        "attempts",
        "max_attempts",
        "created_at",
        "updated_at",
    }
    assert safe_job["kind"] == "pentagi_flow"
    assert safe_job["max_attempts"] == 1
    assert "payload" not in safe_job
    assert "dedupe_key" not in safe_job

    persisted = jobs.get(safe_job["id"])
    assert persisted is not None
    assert persisted["payload"]["request"]
    assert campaign.state == main.CampaignState.running
    assert result["audit_reconciled"] is True
    assert saved and saved[0][1] == 7
    pentagi_events = [
        event["type"]
        for event in campaign.events
        if event["type"].startswith("pentagi_")
    ]
    assert pentagi_events == [
        "pentagi_dispatch_requested",
        "pentagi_flow_queued",
    ]

    repeated = main.dispatch_pentagi_campaign(campaign.id)
    assert repeated["job"]["id"] == safe_job["id"]
    assert jobs.campaign_job_counts(campaign.id)["pentagi_flow"] == 1
    assert sum(
        1
        for event in campaign.events
        if event.get("type") == "pentagi_flow_queued"
        and event.get("job_id") == safe_job["id"]
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
            {
                "id": "a1",
                "kind": "pentagi_receipt",
                "media_type": "application/json",
                "sha256": "a" * 64,
                "size_bytes": 42,
                "created_at": "2026-01-01T00:00:00+00:00",
                "idempotency_key": "internal-receipt-key",
            },
            {
                "id": "a2",
                "kind": "pentagi_status",
                "media_type": "application/json",
                "sha256": "b" * 64,
                "size_bytes": 21,
                "created_at": "2026-01-01T00:01:00+00:00",
                "idempotency_key": "internal-status-key",
            },
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
    assert all("idempotency_key" not in item for item in result["artifacts"])


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
