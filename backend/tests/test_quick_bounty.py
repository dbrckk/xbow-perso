from app.quick_bounty import (
    batch_journal_entry,
    learning_digest,
    select_quick_portfolio,
)


def _program(handle: str, effort: float, efficiency: int, opportunity: int, payout: float):
    return {
        "handle": handle,
        "name": handle.upper(),
        "status": "READY",
        "offers_bounties": True,
        "effort_factor": effort,
        "value_efficiency_score": efficiency,
        "opportunity_score": opportunity,
        "historical_usd_awarded_max": payout,
        "historical_value_score": payout / 1000,
    }


def test_quick_portfolio_selects_six_unique_reviewed_ready_programs():
    programs = [
        _program("a", 1.0, 95, 80, 1000),
        _program("b", 1.0, 90, 78, 2000),
        _program("c", 1.5, 85, 84, 3000),
        _program("d", 1.5, 82, 82, 4000),
        _program("e", 2.0, 70, 90, 50000),
        _program("f", 2.1, 68, 88, 40000),
        _program("g", 1.2, 60, 70, 100),
        {**_program("blocked", 1.0, 99, 99, 999999), "status": "BLOCKED"},
    ]

    result = select_quick_portfolio(programs)

    assert len(result["handles"]) == 6
    assert len(set(result["handles"])) == 6
    assert result["summary"]["easy"] == 2
    assert result["summary"]["medium"] == 2
    assert result["summary"]["high_value"] == 2
    assert "blocked" not in result["handles"]
    assert result["requires_exact_review_profile"] is True
    assert result["automatic_scope_expansion"] is False


def test_quick_portfolio_reports_shortage_instead_of_expanding_scope():
    result = select_quick_portfolio([
        _program("a", 1.0, 90, 80, 1000),
        _program("b", 1.4, 80, 75, 2000),
    ])

    assert result["summary"]["total"] == 2
    assert sum(result["summary"]["shortages"].values()) == 4
    assert result["automatic_scope_expansion"] is False


def test_learning_digest_is_sanitized_and_contains_useful_outcome_metadata():
    campaign = {
        "id": "campaign-1",
        "state": "completed",
        "created_at": "2026-09-21T10:00:00+00:00",
        "updated_at": "2026-09-21T11:00:00+00:00",
        "target": {
            "name": "Program",
            "primary_url": "https://secret-target.example",
        },
        "findings": [
            {
                "title": "Broken access control",
                "severity": "high",
                "status": "confirmed",
                "cwe": "CWE-284",
                "asset": "https://secret-target.example",
                "endpoint": "/private",
                "evidence": ["secret evidence"],
                "discovered_by": "nuclei",
                "validated_by": "independent",
            }
        ],
        "events": [
            {"type": "campaign_started"},
            {"type": "recon_task_completed"},
            {"type": "validation_completed"},
        ],
    }
    batch = {
        "id": "batch-1",
        "mode": "parallel",
        "state": "completed",
        "created_at": "2026-09-21T10:00:00+00:00",
        "updated_at": "2026-09-21T11:00:00+00:00",
        "members": [
            {
                "campaign_id": "campaign-1",
                "handle": "alpha",
                "status": "done",
            }
        ],
    }

    digest = learning_digest(batch, {"campaign-1": campaign})
    encoded = str(digest)

    assert digest["sanitized"] is True
    assert digest["contains_secrets"] is False
    assert digest["contains_evidence_bodies"] is False
    assert digest["contains_target_urls"] is False
    assert digest["totals"]["findings_confirmed"] == 1
    assert "CWE-284" in encoded
    assert "secret-target.example" not in encoded
    assert "secret evidence" not in encoded


def test_batch_journal_keeps_server_side_progress_summary():
    campaign = {
        "id": "campaign-1",
        "state": "running",
        "created_at": "2026-09-21T10:00:00+00:00",
        "updated_at": "2026-09-21T10:05:00+00:00",
        "target": {"name": "Program"},
        "findings": [],
        "events": [{"type": "campaign_started"}],
    }
    batch = {
        "id": "batch-1",
        "mode": "sequential",
        "state": "running",
        "continues_without_dashboard": True,
        "members": [
            {
                "campaign_id": "campaign-1",
                "handle": "alpha",
                "status": "running",
            }
        ],
    }

    journal = batch_journal_entry(batch, {"campaign-1": campaign})

    assert journal["continues_without_dashboard"] is True
    assert journal["members"][0]["campaign"]["state"] == "running"
