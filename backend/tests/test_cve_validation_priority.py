from types import SimpleNamespace

from app.cve_evidence_verdict import build_cve_evidence_verdict
from app.cve_validation_priority import (
    CVE_VALIDATION_PLAN_SCHEMA,
    build_cve_validation_plan,
)


def _finding():
    return SimpleNamespace(
        id="f1",
        cve_ids=["CVE-2026-12345"],
        evidence=["cve-id:CVE-2026-12345"],
        title="fixture",
        summary="",
    )


def test_behaviorally_supported_candidate_gets_safe_active_non_destructive_plan():
    finding = _finding()
    verdict = build_cve_evidence_verdict(
        finding,
        differential_signal="strong",
        versioned_fingerprint_match_count=1,
        high_confidence_fingerprint_match_count=1,
    )

    result = build_cve_validation_plan(finding, verdict=verdict)

    assert result.schema == CVE_VALIDATION_PLAN_SCHEMA
    assert result.validation_mode == "safe_active"
    assert "reproduce_non_destructive_behavior" in result.recommended_checks
    assert result.destructive_testing_allowed is False
    assert result.state_changing_validation_allowed is False
    assert result.exploit_execution_allowed is False
    assert result.automatic_execution_authorized is False
    assert result.independent_validation_required is True


def test_ambiguous_backport_candidate_is_forced_to_passive_recheck():
    finding = _finding()
    verdict = build_cve_evidence_verdict(
        finding,
        differential_signal="strong",
        versioned_fingerprint_match_count=2,
        high_confidence_fingerprint_match_count=2,
        ambiguity_reasons=("possible_backport",),
    )

    result = build_cve_validation_plan(finding, verdict=verdict)

    assert result.validation_mode == "passive_recheck"
    assert "re_fingerprint_product_and_version" in result.recommended_checks
    assert result.exploit_execution_allowed is False


def test_identifier_only_candidate_gets_metadata_recheck():
    finding = _finding()
    verdict = build_cve_evidence_verdict(finding)

    result = build_cve_validation_plan(finding, verdict=verdict)

    assert result.validation_mode == "passive_recheck"
    assert result.recommended_checks == (
        "verify_cve_metadata",
        "verify_product_identity",
        "verify_version_evidence",
    )


def test_non_cve_low_signal_path_is_deferred():
    finding = SimpleNamespace(
        id="f2",
        cve_ids=[],
        evidence=[],
        title="weak anomaly",
        summary="",
    )
    verdict = build_cve_evidence_verdict(finding)

    result = build_cve_validation_plan(finding, verdict=verdict)

    assert result.validation_mode == "defer"
    assert result.recommended_checks == ("collect_more_evidence",)
    assert result.automatic_execution_authorized is False
