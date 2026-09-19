from app.hackerone_attention import build_hackerone_attention_center


def _campaign(campaign_id, state, *, activity=None, nmi=None, bounty=None):
    artifact_id = f"report-{campaign_id}"
    events = [
        {
            "type": "hackerone_report_submitted",
            "artifact_id": artifact_id,
            "remote_report_id": str(1000 + int(campaign_id[-1])),
            "team_handle": "security",
            "at": "2026-09-18T20:00:00+00:00",
        }
    ]
    if state is not None:
        events.append(
            {
                "type": "hackerone_report_status_synced",
                "artifact_id": artifact_id,
                "remote_report_id": str(1000 + int(campaign_id[-1])),
                "team_handle": "security",
                "state": state,
                "observed_at": "2026-09-18T21:00:00+00:00",
            }
        )
    if nmi:
        events.append(
            {
                "type": "hackerone_needs_more_info_observed",
                "artifact_id": artifact_id,
                "remote_report_id": str(1000 + int(campaign_id[-1])),
                "activity_id": "nmi-1",
                "message": "Please provide exact headers.",
                "observed_at": "2026-09-18T21:05:00+00:00",
            }
        )
    if activity:
        events.append(
            {
                "type": "hackerone_public_activity_observed",
                "artifact_id": artifact_id,
                "remote_report_id": str(1000 + int(campaign_id[-1])),
                "activity_id": "activity-1",
                "activity_type": activity,
                "message": "Public update.",
                "observed_at": "2026-09-18T21:10:00+00:00",
            }
        )
    if bounty:
        events.append(
            {
                "type": "hackerone_public_activity_observed",
                "artifact_id": artifact_id,
                "remote_report_id": str(1000 + int(campaign_id[-1])),
                "activity_id": "bounty-1",
                "activity_type": "activity-bounty-awarded",
                "bounty_amount": "500",
                "bonus_amount": "50",
                "observed_at": "2026-09-18T21:15:00+00:00",
            }
        )
    return {
        "id": campaign_id,
        "target": {"name": f"Campaign {campaign_id}"},
        "events": events,
    }


def test_attention_center_classifies_current_report_states():
    result = build_hackerone_attention_center(
        [
            _campaign("c1", "needs-more-info", nmi=True),
            _campaign("c2", "triaged"),
            _campaign("c3", "resolved"),
            _campaign("c4", "duplicate"),
            _campaign("c5", "informative"),
        ]
    )

    by_campaign = {item["campaign_id"]: item for item in result["items"]}
    assert by_campaign["c1"]["bucket"] == "action-required"
    assert by_campaign["c1"]["action_required"] is True
    assert by_campaign["c1"]["needs_more_info"]["message"] == "Please provide exact headers."
    assert by_campaign["c2"]["bucket"] == "active"
    assert by_campaign["c3"]["bucket"] == "resolved"
    assert by_campaign["c4"]["bucket"] == "duplicate"
    assert by_campaign["c5"]["bucket"] == "informative"
    assert result["summary"]["action_required"] == 1
    assert result["summary"]["active"] == 1
    assert result["summary"]["resolved"] == 1
    assert result["summary"]["duplicate"] == 1
    assert result["summary"]["informative"] == 1
    assert result["read_only"] is True
    assert result["source"] == "local_audit_events"


def test_attention_center_tracks_bounty_without_changing_state_bucket():
    result = build_hackerone_attention_center(
        [_campaign("c1", "triaged", bounty=True)]
    )

    item = result["items"][0]
    assert item["bucket"] == "active"
    assert item["bounty"] == {
        "activity_id": "bounty-1",
        "amount": "500",
        "bonus_amount": "50",
        "observed_at": "2026-09-18T21:15:00+00:00",
    }
    assert result["summary"]["with_bounty"] == 1


def test_attention_center_marks_unsynced_submission_without_remote_call():
    result = build_hackerone_attention_center([_campaign("c1", None)])

    item = result["items"][0]
    assert item["bucket"] == "awaiting-sync"
    assert item["state"] is None
    assert item["action_required"] is False


def test_attention_center_ignores_campaigns_without_recorded_submission():
    result = build_hackerone_attention_center(
        [
            {
                "id": "local-only",
                "target": {"name": "Local only"},
                "events": [{"type": "hackerone_report_status_synced", "state": "triaged"}],
            }
        ]
    )

    assert result["summary"]["total"] == 0
    assert result["items"] == []


def test_attention_center_keeps_latest_submission_per_artifact():
    campaign = _campaign("c1", "triaged")
    campaign["events"].insert(
        0,
        {
            "type": "hackerone_report_submitted",
            "artifact_id": "report-c1",
            "remote_report_id": "999",
            "team_handle": "old-team",
            "at": "2026-09-18T19:00:00+00:00",
        },
    )

    result = build_hackerone_attention_center([campaign])

    assert result["items"][0]["remote_report_id"] == "1001"
    assert result["items"][0]["team_handle"] == "security"
