from app.hackerone_quick import build_batch_learning_brief, select_quick_six


def _program(
    handle: str,
    *,
    effort: float,
    award: float = 0.0,
    historical: float = 0.0,
    status: str = "READY",
):
    return {
        "handle": handle,
        "name": handle.title(),
        "status": status,
        "offers_bounties": True,
        "effort_factor": effort,
        "value_efficiency_score": 80,
        "opportunity_score": 70,
        "local_cost_efficiency_score": 0,
        "historical_usd_awarded_max": award,
        "historical_value_score": historical,
    }


def test_quick_selector_returns_two_per_group_without_overlap():
    result = select_quick_six([
        _program("high-one", effort=2.0, award=50000, historical=90),
        _program("high-two", effort=1.8, award=25000, historical=80),
        _program("easy-one", effort=1.0),
        _program("easy-two", effort=1.1),
        _program("medium-one", effort=1.5),
        _program("medium-two", effort=1.6),
        _program("blocked", effort=1.0, award=90000, status="BLOCKED"),
    ])

    assert result["complete"] is True
    assert [item["handle"] for item in result["groups"]["high_value"]] == [
        "high-one",
        "high-two",
    ]
    assert [item["handle"] for item in result["groups"]["easy"]] == [
        "easy-one",
        "easy-two",
    ]
    assert [item["handle"] for item in result["groups"]["medium"]] == [
        "medium-one",
        "medium-two",
    ]
    assert len(result["handles"]) == len(set(result["handles"])) == 6
    assert result["ready_only"] is True
    assert result["scope_expansion"] is False


def test_quick_selector_refuses_to_fake_second_high_value_slot():
    result = select_quick_six([
        _program("high-one", effort=2.0, award=50000, historical=90),
        _program("easy-one", effort=1.0),
        _program("easy-two", effort=1.1),
        _program("medium-one", effort=1.4),
        _program("medium-two", effort=1.5),
        _program("other", effort=1.7),
    ])

    assert len(result["groups"]["high_value"]) == 1
    assert result["complete"] is False
    assert result["selected"] == 5


class _Store:
    def __init__(self):
        self.campaigns = {
            "c1": {
                "id": "c1",
                "state": "completed",
                "created_at": "2026-09-21T12:00:00+00:00",
                "updated_at": "2026-09-21T13:00:00+00:00",
                "target": {"name": "Alpha"},
                "findings": [
                    {
                        "title": "Confirmed issue",
                        "severity": "high",
                        "status": "confirmed",
                        "impact": "bounded impact",
                        "cwe": "CWE-200",
                        "cvss": 7.5,
                    }
                ],
                "events": [
                    {
                        "type": "worker_outcome",
                        "job_id": "j1",
                        "job_kind": "nuclei_scan",
                        "success": True,
                        "status": "completed",
                        "attempts": 0,
                        "at": "2026-09-21T12:30:00+00:00",
                    }
                ],
            }
        }

    def get_campaign(self, campaign_id):
        return self.campaigns.get(campaign_id)

    def list_observations(self, campaign_id):
        return []


def test_batch_learning_brief_is_sanitized_and_detailed():
    brief = build_batch_learning_brief(
        _Store(),
        {
            "id": "batch-1",
            "mode": "sequential",
            "state": "completed",
            "created_at": "2026-09-21T12:00:00+00:00",
            "updated_at": "2026-09-21T13:00:00+00:00",
            "summary": {"done": 1},
            "members": [
                {
                    "campaign_id": "c1",
                    "handle": "alpha",
                    "status": "done",
                }
            ],
        },
    )

    assert brief["totals"]["confirmed_findings"] == 1
    assert brief["totals"]["high_critical_confirmed"] == 1
    assert brief["campaigns"][0]["worker_outcomes"]["totals"]["completed"] == 1
    assert brief["contains_secrets"] is False
    assert brief["contains_raw_job_payloads"] is False
    assert brief["automatic_code_merge"] is False
