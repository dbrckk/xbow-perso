from types import SimpleNamespace

from app.public_duplicate_intelligence import rank_public_duplicate_risk


def _finding(
    title="GraphQL authorization bypass",
    summary="Role user can read admin object",
    cwe="CWE-862",
):
    return SimpleNamespace(title=title, summary=summary, cwe=cwe)


def test_same_program_public_match_raises_similarity_without_blocking():
    reports = [
        {
            "id": "r1",
            "title": "GraphQL authorization bypass exposes admin object",
            "summary": "Authorization issue lets a user read an admin object",
            "cwe": "CWE-862",
            "program_handle": "alpha",
            "url": "https://hackerone.com/reports/1",
            "severity": "high",
        }
    ]

    result = rank_public_duplicate_risk(
        _finding(),
        reports,
        program_handle="alpha",
    )

    assert result["similarity_signal"] > 0.35
    assert result["matches"][0]["same_program"] is True
    assert result["automatic_report_block"] is False
    assert result["does_not_predict_platform_duplicate_decision"] is True
    assert result["network_requests_sent"] == 0


def test_unrelated_public_reports_keep_low_similarity():
    reports = [
        {
            "id": "r2",
            "title": "Stored XSS in profile biography",
            "summary": "A script executes in profile rendering",
            "cwe": "CWE-79",
            "program_handle": "beta",
        }
    ]

    result = rank_public_duplicate_risk(
        _finding(),
        reports,
        program_handle="alpha",
    )

    assert result["similarity_signal"] < 0.35
    assert result["novelty_signal"] > 0.65


def test_public_duplicate_similarity_is_bounded_and_read_only():
    reports = [
        {
            "id": f"r{index}",
            "title": "GraphQL authorization bypass",
            "summary": "admin object",
            "cwe": "CWE-862",
        }
        for index in range(700)
    ]

    result = rank_public_duplicate_risk(
        _finding(),
        reports,
        program_handle="alpha",
        limit=3,
    )

    assert result["reports_compared"] == 500
    assert len(result["matches"]) <= 3
    assert result["public_subset_only"] is True
    assert result["advisory_only"] is True
    assert result["automatic_report_block"] is False
    assert result["network_requests_sent"] == 0


def test_public_duplicate_similarity_rejects_unbounded_match_limit():
    try:
        rank_public_duplicate_risk(_finding(), [], limit=11)
    except ValueError as exc:
        assert "between 1 and 10" in str(exc)
    else:
        raise AssertionError("expected bounded match limit")
