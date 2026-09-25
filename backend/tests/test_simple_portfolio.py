from app.simple_portfolio import mark_cached_review_profiles, select_simple_six


def _program(handle, *, effort, efficiency, award):
    return {
        "handle": handle,
        "name": handle.upper(),
        "status": "READY",
        "offers_bounties": True,
        "gold_standard_safe_harbor": True,
        "effort_factor": effort,
        "value_efficiency_score": efficiency,
        "opportunity_score": efficiency,
        "historical_usd_awarded_max": award,
        "historical_value_score": min(100, award / 1000),
    }


def test_simple_six_is_disjoint_and_complete():
    programs = [
        _program("a", effort=0.5, efficiency=95, award=100),
        _program("b", effort=0.6, efficiency=90, award=200),
        _program("c", effort=1.2, efficiency=80, award=300),
        _program("d", effort=1.4, efficiency=75, award=400),
        _program("e", effort=2.0, efficiency=70, award=50000),
        _program("f", effort=2.2, efficiency=65, award=40000),
        _program("g", effort=3.0, efficiency=60, award=1000),
        _program("h", effort=3.5, efficiency=55, award=2000),
    ]
    result = select_simple_six(programs)

    assert result["complete"] is True
    assert result["selection_count"] == 6
    assert len(set(result["handles"])) == 6
    assert len(result["groups"]["easy"]) == 2
    assert len(result["groups"]["medium"]) == 2
    assert len(result["groups"]["high_value"]) == 2


def test_simple_six_can_propose_review_candidates_without_gold_standard_badge():
    programs = [
        _program("ready", effort=1, efficiency=90, award=1000),
        {
            **_program("review", effort=0.1, efficiency=100, award=999999),
            "status": "REVIEW",
            "gold_standard_safe_harbor": True,
        },
        {
            **_program("unsafe-review", effort=0.1, efficiency=100, award=999999),
            "status": "REVIEW",
            "gold_standard_safe_harbor": False,
        },
        {**_program("free", effort=0.1, efficiency=100, award=999999), "offers_bounties": False},
    ]
    result = select_simple_six(programs)

    assert "ready" in result["handles"]
    assert "review" in result["handles"]
    assert "unsafe-review" in result["handles"]
    assert "free" not in result["handles"]
    assert result["review_count"] == 2
    assert result["launch_ready"] is False
    assert result["complete"] is False



def test_cached_review_profile_is_deferred_for_launch_revalidation():
    programs = [{
        **_program("reviewed", effort=1.0, efficiency=88, award=5000),
        "status": "REVIEW",
        "review_profile_available": True,
        "reasons": ["saved_profile_requires_snapshot_revalidation"],
    }]
    result = mark_cached_review_profiles(programs)
    assert result[0]["status"] == "REVALIDATE"
    assert result[0]["revalidation_deferred"] is True
    assert "saved_profile_will_be_revalidated_at_launch" in result[0]["reasons"]


def test_simple_six_allows_revalidation_without_forcing_first_run_review():
    programs = [
        {
            **_program(chr(97 + index), effort=0.5 + index, efficiency=90 - index, award=1000 * (index + 1)),
            "status": "REVALIDATE",
            "review_profile_available": True,
        }
        for index in range(6)
    ]
    result = select_simple_six(programs)
    assert result["complete"] is True
    assert result["review_count"] == 0
    assert result["revalidation_count"] == 6
    assert result["launch_ready"] is True


def test_gold_standard_badge_is_only_a_review_ranking_signal():
    programs = [
        {
            **_program("badge", effort=1.0, efficiency=80, award=1000),
            "status": "REVIEW",
            "gold_standard_safe_harbor": True,
        },
        {
            **_program("no-badge", effort=0.1, efficiency=99, award=9999),
            "status": "REVIEW",
            "gold_standard_safe_harbor": False,
        },
    ]
    result = select_simple_six(programs)

    assert result["handles"][0] == "badge"
    assert "no-badge" in result["handles"]
