from app.opportunity_ranking import build_opportunity_signal


def test_ready_high_value_runtime_match_scores_above_review():
    program = {
        "offers_bounties": True,
        "gold_standard_safe_harbor": True,
    }
    signal = {
        "historical_value_score": 18,
        "high_critical_count": 3,
        "disclosed_report_count": 4,
        "usd_awarded_max": 25000,
        "top_categories": ["api_graphql", "access_control"],
    }
    runtime = {"recon": True, "browser": True, "scanner": False}

    ready = build_opportunity_signal(
        status="READY",
        program=program,
        signal=signal,
        runtime=runtime,
        is_new=True,
        is_changed=False,
    )
    review = build_opportunity_signal(
        status="REVIEW",
        program=program,
        signal=signal,
        runtime=runtime,
        is_new=True,
        is_changed=False,
    )

    assert ready["opportunity_score"] > review["opportunity_score"]
    assert "api_graphql" in ready["runtime_ready_categories"]
    assert "access_control" in ready["runtime_ready_categories"]
    assert ready["automatic_launch"] is False
    assert ready["scope_expansion"] is False


def test_blocked_program_never_receives_opportunity_score():
    result = build_opportunity_signal(
        status="BLOCKED",
        program={"offers_bounties": True, "gold_standard_safe_harbor": True},
        signal={
            "historical_value_score": 100,
            "high_critical_count": 10,
            "disclosed_report_count": 10,
            "usd_awarded_max": 100000,
            "top_categories": ["injection_rce"],
        },
        runtime={"scanner": True},
        is_new=True,
        is_changed=False,
    )

    assert result["opportunity_score"] == 0


def test_runtime_focus_prefers_categories_currently_supported():
    result = build_opportunity_signal(
        status="READY",
        program={"offers_bounties": True},
        signal={
            "top_categories": ["injection_rce", "api_graphql"],
        },
        runtime={"scanner": False, "recon": True, "browser": True},
        is_new=False,
        is_changed=False,
    )

    assert result["research_focus"][0] == "api_graphql"
    assert "injection_rce" not in result["runtime_ready_categories"]
    assert result["historical_signals_are_not_expected_payout"] is True
