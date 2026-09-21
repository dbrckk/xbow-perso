from types import SimpleNamespace

from app.public_duplicate_intelligence import rank_public_duplicate_risk


def _finding(title="GraphQL authorization bypass", summary="Role user can read admin object", cwe="CWE-862"):
    return SimpleNamespace(title=title, summary=summary, cwe=cwe)


def test_same_program_public_match_raises_duplicate_risk_without_blocking():
    reports = [
        {
            "id": "r1",
            "title": "GraphQL authorization bypass exposes admin object",
            "summary": "Authorization issue lets a user read an admin object",
            "cwe": "CWE-862",
            "program_handle": "alpha",
            "url": "https://hackerone.com/reports/1",
            "severity": "high",
            "award_amount": 5000,
            "currency": "USD",
        }
    ]

    result = rank_public_duplicate_risk(
        _finding(),
        reports,
        program_handle="alpha",
    )

    assert result["risk_score"] > 0.35
    assert result["matches"][0]["same_program"] is True
    assert result["automatic_report_block"] is False
    assert result["does_not_predict_platform_duplicate_decision"] is True


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

    assert result["risk_score"] < 0.35
    assert result["novelty_score"] > 0.65


def test_public_duplicate_risk_is_bounded_and_read_only():
    result = rank_public_duplicate_risk(_finding(), [], program_handle="alpha")

    assert result["risk_score"] == 0
    assert result["novelty_score"] == 1
    assert result["public_subset_only"] is True
    assert result["advisory_only"] is True
