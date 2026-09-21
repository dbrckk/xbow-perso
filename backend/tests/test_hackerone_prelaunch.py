from fastapi import HTTPException

from app import hackerone_api


def test_remote_program_launch_gate_blocks_closed_states():
    assert hackerone_api._remote_program_launch_block_reason(
        {"submission_state": "closed", "state": "public_mode"}
    ) == "program_submissions_not_open"
    assert hackerone_api._remote_program_launch_block_reason(
        {"submission_state": "open", "state": "archived"}
    ) == "program_not_currently_open"


def test_remote_program_launch_gate_allows_open_program():
    assert hackerone_api._remote_program_launch_block_reason(
        {"submission_state": "open", "state": "public_mode"}
    ) is None


def test_server_discovery_selection_is_read_only_and_bounded(monkeypatch):
    programs = [
        {
            "handle": "alpha",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 90,
            "opportunity_score": 90,
            "research_focus": ["api_graphql"],
            "reasons": [],
            "opportunity_reasons": [],
        },
        {
            "handle": "beta",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 80,
            "opportunity_score": 85,
            "research_focus": ["access_control"],
            "reasons": [],
            "opportunity_reasons": [],
        },
        {
            "handle": "review",
            "status": "REVIEW",
            "offers_bounties": True,
            "value_efficiency_score": 100,
            "opportunity_score": 100,
            "research_focus": ["auth_session"],
            "reasons": [],
            "opportunity_reasons": [],
        },
    ]

    monkeypatch.setattr(
        hackerone_api,
        "hackerone_program_discovery",
        lambda verify_limit=50: {
            "programs": programs,
            "catalog_checked_at": "2026-09-21T10:00:00+00:00",
        },
    )

    result = hackerone_api.hackerone_discovery_selection(limit=2, min_score=50)

    assert result["handles"] == ["alpha", "beta"]
    assert result["read_only"] is True
    assert result["automatic_launch"] is False
    assert result["scope_expansion"] is False
    assert result["requires_launch_revalidation"] is True


def test_reviewed_campaign_input_blocks_program_that_closed_after_review(monkeypatch):
    class Snapshot:
        handle = "alpha"
        snapshot_sha256 = "a" * 64
        program = {
            "name": "Alpha",
            "submission_state": "closed",
            "state": "public_mode",
        }
        document = {"data": []}

    class Store:
        def get_hackerone_review_profile(self, _profile_id):
            raise AssertionError("profile lookup should not happen after close-state gate")

    monkeypatch.setattr(
        hackerone_api,
        "fetch_hackerone_program_snapshot",
        lambda _handle: Snapshot(),
    )

    try:
        hackerone_api._reviewed_campaign_input("alpha", Store())
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail["reason"] == "program_submissions_not_open"
    else:
        raise AssertionError("closed program should be blocked")
