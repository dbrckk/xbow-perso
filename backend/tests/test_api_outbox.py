import pytest

from app import main
from app.api_outbox import outbox_snapshot
from app.main import Campaign, ProgramRules, TargetInput


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
