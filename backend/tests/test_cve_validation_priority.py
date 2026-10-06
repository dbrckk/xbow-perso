from types import SimpleNamespace

from app.cve_evidence_verdict import build_cve_evidence_verdict
from app.cve_validation_priority import build_cve_validation_priority


def _finding(*, severity="high", epss_score=None):
    return SimpleNamespace(
        id="f1",
        severity=severity,
        epss_score=epss_score,
        cve_ids=["CVE-2026-12345"],
        evidence=["cve-id:CVE-2026-12345"],
        title="fixture",
        summary="",
    )


def test_behaviorally_supported_high_risk_candidate_is_prioritized_without_exploit_execution():
    finding = _finding(severity="critical", epss_score=0.8)
    verdict = build_cve_evidence_verdict(
        finding,
        differential_signal="strong",
        versioned_fingerprint_match_count=1,
        high_confidence_fingerprint_match_count=1,
    )

    result = build_cve_validation_priority(
        finding,
        verdict=verdict,
        corroborating_source_count=2,
    )

    assert result.priority_band == "urgent"
    assert result.validation_mode == "safe_active"
    assert "reproduce_non_destructive_behavior" in result.recommended_checks
    assert result.destructive_testing_allowed is False
    assert result.state_changing_validation_allowed is False
    assert result.exploit_execution_allowed is False
    assert result.independent_validation_required is True


def test_ambiguous_backport_candidate_is_forced_to_passive_recheck():
    finding = _finding(severity="critical", epss_score=0.9)
    verdict = build_cve_evidence_verdict(
        finding,
        differential_signal="strong",
        versioned_fingerprint_match_count=2,
        high_confidence_fingerprint_match_count=2,
        ambiguity_reasons=("possible_backport",),
    )

    result = build_cve_validation_priority(
        finding,
        verdict=verdict,
        corroborating_source_count=2,
    )

    assert result.validation_mode == "passive_recheck"
    assert "version_ambiguity" in result.reasons
    assert "re_fingerprint_product_and_version" in result.recommended_checks
    assert result.exploit_execution_allowed is False


def test_identifier_only_candidate_gets_metadata_recheck():
    finding = _finding(severity="medium")
    verdict = build_cve_evidence_verdict(finding)

    result = build_cve_validation_priority(
        finding,
        verdict=verdict,
        corroborating_source_count=1,
    )

    assert result.validation_mode == "passive_recheck"
    assert "verify_cve_metadata" in result.recommended_checks
    assert "identifier_only" in result.reasons


def test_epss_is_priority_signal_not_exploitability_confirmation():
    finding = _finding(severity="high", epss_score=0.95)
    verdict = build_cve_evidence_verdict(
        finding,
        versioned_fingerprint_match_count=1,
        high_confidence_fingerprint_match_count=1,
    )

    result = build_cve_validation_priority(
        finding,
        verdict=verdict,
        corroborating_source_count=2,
    )

    assert "high_epss" in result.reasons
    assert result.priority_score > 0
    assert result.exploit_execution_allowed is False
