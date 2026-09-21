from app.chain_intelligence import build_chain_intelligence


def _category(name: str, evidence: float, high: int = 0, award: float = 0) -> dict:
    return {
        "category": name,
        "evidence_score": evidence,
        "high_critical_count": high,
        "usd_awarded_max": award,
    }


def test_named_chain_is_ranked_without_execution():
    result = build_chain_intelligence(
        [
            _category("ssrf_oob", 12, 2, 25000),
            _category("information_disclosure", 8, 1, 5000),
            _category("cloud_surface", 7, 1, 10000),
        ]
    )
    candidate = next(item for item in result["candidates"] if item["chain_id"] == "ssrf-disclosure-cloud")
    assert candidate["completeness"] == 1.0
    assert candidate["historical_usd_award_max"] == 25000
    assert candidate["advisory_only"] is True
    assert candidate["automatic_execution"] is False
    assert result["automatic_execution"] is False


def test_partial_chain_remains_hypothesis():
    result = build_chain_intelligence(
        [
            _category("ai_llm", 20, 3),
            _category("access_control", 18, 2),
        ]
    )
    candidate = next(item for item in result["candidates"] if item["chain_id"] == "ai-agent-access")
    assert candidate["completeness"] < 1
    assert candidate["missing_categories"] == ["api_graphql"]


def test_single_family_does_not_invent_chain():
    result = build_chain_intelligence([_category("business_logic", 50, 10)])
    assert result["candidates"] == []
