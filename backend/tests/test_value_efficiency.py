from app.value_efficiency import (
    build_value_efficiency_signal,
    select_diversified_portfolio,
)


def test_ready_runtime_match_has_better_efficiency_than_review_gap():
    ready = build_value_efficiency_signal(
        status="READY",
        opportunity_score=80,
        research_focus=["api_graphql"],
        runtime_ready_categories=["api_graphql"],
        runtime_partial_categories=[],
        gold_standard_safe_harbor=True,
    )
    review = build_value_efficiency_signal(
        status="REVIEW",
        opportunity_score=80,
        research_focus=["api_graphql"],
        runtime_ready_categories=[],
        runtime_partial_categories=[],
        gold_standard_safe_harbor=False,
    )

    assert ready["value_efficiency_score"] > review["value_efficiency_score"]
    assert ready["effort_factor"] < review["effort_factor"]
    assert ready["automatic_launch"] is False
    assert ready["scope_expansion"] is False


def test_blocked_efficiency_is_zero():
    result = build_value_efficiency_signal(
        status="BLOCKED",
        opportunity_score=100,
        research_focus=["injection_rce"],
        runtime_ready_categories=["injection_rce"],
        runtime_partial_categories=[],
        gold_standard_safe_harbor=True,
    )

    assert result["value_efficiency_score"] == 0


def test_portfolio_only_selects_ready_bounty_above_threshold():
    programs = [
        {
            "handle": "ready",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 80,
            "opportunity_score": 85,
            "research_focus": ["api_graphql"],
        },
        {
            "handle": "review",
            "status": "REVIEW",
            "offers_bounties": True,
            "value_efficiency_score": 95,
            "opportunity_score": 95,
            "research_focus": ["access_control"],
        },
        {
            "handle": "no-bounty",
            "status": "READY",
            "offers_bounties": False,
            "value_efficiency_score": 99,
            "opportunity_score": 99,
            "research_focus": ["auth_session"],
        },
        {
            "handle": "low",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 40,
            "opportunity_score": 90,
            "research_focus": ["ssrf_oob"],
        },
    ]

    result = select_diversified_portfolio(programs, limit=5, min_score=50)

    assert [item["handle"] for item in result] == ["ready"]


def test_portfolio_diversifies_primary_focus():
    programs = [
        {
            "handle": "api-a",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 90,
            "opportunity_score": 90,
            "research_focus": ["api_graphql"],
        },
        {
            "handle": "api-b",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 88,
            "opportunity_score": 90,
            "research_focus": ["api_graphql"],
        },
        {
            "handle": "access",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 84,
            "opportunity_score": 86,
            "research_focus": ["access_control"],
        },
    ]

    result = select_diversified_portfolio(programs, limit=2, min_score=50)

    assert [item["handle"] for item in result] == ["api-a", "access"]
    assert result[1]["portfolio_concentration_penalty"] == 0



def test_portfolio_reserves_bounded_exploration_slot_for_fresh_ready_program():
    programs = [
        {
            "handle": "stable-a",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 95,
            "opportunity_score": 95,
            "research_focus": ["api_graphql"],
            "reasons": [],
            "opportunity_reasons": [],
        },
        {
            "handle": "stable-b",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 93,
            "opportunity_score": 94,
            "research_focus": ["access_control"],
            "reasons": [],
            "opportunity_reasons": [],
        },
        {
            "handle": "stable-c",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 92,
            "opportunity_score": 93,
            "research_focus": ["auth_session"],
            "reasons": [],
            "opportunity_reasons": [],
        },
        {
            "handle": "stable-d",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 91,
            "opportunity_score": 92,
            "research_focus": ["ssrf_oob"],
            "reasons": [],
            "opportunity_reasons": [],
        },
        {
            "handle": "fresh",
            "status": "READY",
            "offers_bounties": True,
            "value_efficiency_score": 80,
            "opportunity_score": 90,
            "research_focus": ["information_disclosure"],
            "reasons": ["new_program"],
            "opportunity_reasons": ["new_program"],
        },
    ]

    result = select_diversified_portfolio(programs, limit=4, min_score=50)

    assert len(result) == 4
    assert "fresh" in [item["handle"] for item in result]
    fresh = next(item for item in result if item["handle"] == "fresh")
    assert fresh["portfolio_exploration_slot"] is True
