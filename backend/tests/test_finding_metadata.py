from types import SimpleNamespace

from app.finding_metadata import (
    assess_finding_metadata,
    cvss_qualitative_rating,
    normalize_cwe,
    normalize_cvss_score,
    severity_matches_cvss,
)


def test_cwe_normalization_is_canonical_and_fail_closed():
    assert normalize_cwe(" cwe-79 ") == "CWE-79"
    assert normalize_cwe("CWE-200") == "CWE-200"
    assert normalize_cwe("CWE-0") is None
    assert normalize_cwe("79") is None
    assert normalize_cwe(None) is None


def test_cvss_normalization_rejects_invalid_or_non_finite_values():
    assert normalize_cvss_score(7.5) == 7.5
    assert normalize_cvss_score(0) == 0.0
    assert normalize_cvss_score(True) is None
    assert normalize_cvss_score(float("nan")) is None
    assert normalize_cvss_score(float("inf")) is None
    assert normalize_cvss_score(-0.1) is None
    assert normalize_cvss_score(10.1) is None


def test_cvss_v3_qualitative_bands():
    assert cvss_qualitative_rating(0.0) == "none"
    assert cvss_qualitative_rating(0.1) == "low"
    assert cvss_qualitative_rating(3.9) == "low"
    assert cvss_qualitative_rating(4.0) == "medium"
    assert cvss_qualitative_rating(6.9) == "medium"
    assert cvss_qualitative_rating(7.0) == "high"
    assert cvss_qualitative_rating(8.9) == "high"
    assert cvss_qualitative_rating(9.0) == "critical"
    assert cvss_qualitative_rating(10.0) == "critical"


def test_severity_consistency_treats_zero_cvss_as_info():
    assert severity_matches_cvss("info", 0.0) is True
    assert severity_matches_cvss("low", 0.0) is False
    assert severity_matches_cvss("high", 7.5) is True
    assert severity_matches_cvss("medium", 7.5) is False


def test_assessment_is_advisory_and_does_not_mutate_finding():
    finding = SimpleNamespace(cwe=" cwe-200 ", cvss=5.3, severity="medium")

    assessment = assess_finding_metadata(finding)

    assert assessment.canonical_cwe == "CWE-200"
    assert assessment.cvss_score == 5.3
    assert assessment.cvss_rating == "medium"
    assert assessment.severity_cvss_consistent is True
    assert finding.cwe == " cwe-200 "
