from app.local_outcome_intelligence import build_local_outcome_signals


def _campaign(
    handle,
    *,
    state="completed",
    findings=None,
    submitted=0,
    created_at="2026-09-21T08:00:00+00:00",
    updated_at="2026-09-21T10:00:00+00:00",
):
    events = [
        {
            "type": "hackerone_policy_bound",
            "remote_binding": {"verified": True, "handle": handle},
        }
    ]
    events.extend(
        {"type": "hackerone_report_submitted"}
        for _ in range(submitted)
    )
    return {
        "state": state,
        "created_at": created_at,
        "updated_at": updated_at,
        "events": events,
        "findings": list(findings or []),
    }


def test_local_outcome_signal_counts_confirmed_and_submitted_reports():
    campaigns = [
        _campaign(
            "alpha",
            findings=[
                {"status": "confirmed", "severity": "high"},
                {"status": "confirmed", "severity": "medium"},
                {"status": "rejected", "severity": "critical"},
            ],
            submitted=1,
        ),
        _campaign("alpha", findings=[], submitted=0),
    ]

    signal = build_local_outcome_signals(campaigns)["alpha"]

    assert signal["campaign_count"] == 2
    assert signal["terminal_campaign_count"] == 2
    assert signal["successful_campaign_count"] == 1
    assert signal["confirmed_finding_count"] == 2
    assert signal["high_critical_confirmed_count"] == 1
    assert signal["submitted_report_count"] == 1
    assert signal["local_outcome_score"] > 0
    assert signal["automatic_launch"] is False
    assert signal["scope_expansion"] is False


def test_unverified_binding_is_ignored():
    campaigns = [
        {
            "state": "completed",
            "events": [
                {
                    "type": "hackerone_policy_bound",
                    "remote_binding": {"verified": False, "handle": "alpha"},
                }
            ],
            "findings": [{"status": "confirmed", "severity": "critical"}],
        }
    ]

    assert build_local_outcome_signals(campaigns) == {}


def test_running_campaign_does_not_inflate_terminal_success_rate():
    campaigns = [
        _campaign(
            "alpha",
            state="running",
            findings=[{"status": "confirmed", "severity": "high"}],
        )
    ]

    signal = build_local_outcome_signals(campaigns)["alpha"]

    assert signal["campaign_count"] == 1
    assert signal["terminal_campaign_count"] == 0
    assert signal["successful_campaign_count"] == 0
    assert signal["smoothed_success_rate"] == 0.25



def test_local_cost_efficiency_uses_terminal_duration_and_events():
    campaigns = [
        _campaign(
            "alpha",
            findings=[{"status": "confirmed", "severity": "high"}],
            submitted=1,
            created_at="2026-09-21T08:00:00+00:00",
            updated_at="2026-09-21T10:00:00+00:00",
        )
        for _ in range(5)
    ]

    signal = build_local_outcome_signals(campaigns)["alpha"]

    assert signal["average_terminal_duration_hours"] == 2.0
    assert signal["average_terminal_event_count"] >= 2.0
    assert signal["local_cost_efficiency_score"] > 0
    assert signal["local_cost_efficiency_score"] <= 10
