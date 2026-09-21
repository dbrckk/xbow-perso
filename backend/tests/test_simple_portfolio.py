from app.simple_portfolio import select_simple_six


def _program(handle, *, effort, efficiency, award):
    return {
        "handle": handle,
        "name": handle.upper(),
        "status": "READY",
        "offers_bounties": True,
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


def test_simple_six_never_selects_unreviewed_or_non_bounty_programs():
    programs = [
        _program("ready", effort=1, efficiency=90, award=1000),
        {**_program("review", effort=0.1, efficiency=100, award=999999), "status": "REVIEW"},
        {**_program("free", effort=0.1, efficiency=100, award=999999), "offers_bounties": False},
    ]
    result = select_simple_six(programs)

    assert result["handles"] == ["ready"]
    assert result["complete"] is False
