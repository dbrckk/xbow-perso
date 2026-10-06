from types import SimpleNamespace

from app.cve_evidence_verdict import (
    CVE_EVIDENCE_VERDICT_SCHEMA,
    build_cve_evidence_verdict,
)


def _finding(*, evidence=None):
    return SimpleNamespace(
        id="f1",
        evidence=list(evidence or ["cve-id:CVE-2026-12345"]),
        cve_ids=["CVE-2026-12345"],
        title="fixture",
        summary="",
    )


def test_identifier_only_never_confirms_exploitability():
    result = build_cve_evidence_verdict(_finding())

    assert result.schema == CVE_EVIDENCE_VERDICT_SCHEMA
    assert result.verdict == "identifier_only_candidate"
    assert result.confidence == "low"
    assert result.exploitability_confirmed is False
    assert result.independent_validation_required is True


def test_version_match_is_candidate_not_confirmation():
    result = build_cve_evidence_verdict(
        _finding(),
        versioned_fingerprint_match_count=1,
        high_confidence_fingerprint_match_count=1,
    )

    assert result.verdict == "high_confidence_version_candidate"
    assert result.confidence == "medium"
    assert result.exploitability_confirmed is False


def test_strong_behavior_plus_high_confidence_version_is_high_confidence_candidate():
    result = build_cve_evidence_verdict(
        _finding(),
        differential_signal="strong",
        versioned_fingerprint_match_count=1,
        high_confidence_fingerprint_match_count=1,
    )

    assert result.verdict == "behaviorally_supported_cve_candidate"
    assert result.confidence == "high"
    assert result.behavioral_evidence is True
    assert result.exploitability_confirmed is False


def test_backport_or_banner_ambiguity_downgrades_even_strong_candidate():
    result = build_cve_evidence_verdict(
        _finding(),
        differential_signal="strong",
        versioned_fingerprint_match_count=2,
        high_confidence_fingerprint_match_count=2,
        ambiguity_reasons=("possible_backport", "banner_version_ambiguous"),
    )

    assert result.verdict == "ambiguous_version_candidate"
    assert result.confidence == "low"
    assert result.ambiguity_reasons == (
        "banner_version_ambiguous",
        "possible_backport",
    )
    assert result.exploitability_confirmed is False


def test_non_cve_finding_is_not_promoted():
    finding = SimpleNamespace(
        id="unknown",
        evidence=[],
        cve_ids=[],
        title="behavioral anomaly",
        summary="",
    )
    result = build_cve_evidence_verdict(
        finding,
        differential_signal="strong",
        versioned_fingerprint_match_count=3,
        high_confidence_fingerprint_match_count=3,
    )

    assert result.verdict == "not_a_cve_candidate"
    assert result.confidence == "none"
