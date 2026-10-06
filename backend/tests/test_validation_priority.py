from types import SimpleNamespace

from app.validation_priority import (
    VALIDATION_PRIORITY_SCHEMA,
    build_validation_priority,
)


def _finding(*, severity="high", status="validation_required"):
    return SimpleNamespace(id="f1", severity=severity, status=status)


def _cve(verdict, *, ambiguity=()):
    return SimpleNamespace(
        verdict=verdict,
        ambiguity_reasons=tuple(ambiguity),
    )


def _vuln(*, known=False, novel=False):
    return SimpleNamespace(
        known_cve_candidate=known,
        novel_candidate=novel,
    )


def test_behaviorally_supported_critical_cve_is_urgent_but_not_auto_executed():
    result = build_validation_priority(
        _finding(severity="critical"),
        cve_verdict=_cve("behaviorally_supported_cve_candidate"),
        vulnerability_signal=_vuln(known=True),
        differential_signal="strong",
        triage_score=0.9,
    )

    assert result.schema == VALIDATION_PRIORITY_SCHEMA
    assert result.band == "urgent"
    assert result.recommended_state == "safe_active_validation"
    assert result.automatic_execution_authorized is False
    assert result.non_destructive_only is True
    assert result.independent_validation_required is True


def test_identifier_only_candidate_is_not_urgent():
    result = build_validation_priority(
        _finding(severity="high"),
        cve_verdict=_cve("identifier_only_candidate"),
        vulnerability_signal=_vuln(known=True),
        triage_score=0.2,
    )

    assert result.band in {"medium", "low"}
    assert result.automatic_execution_authorized is False


def test_version_ambiguity_forces_passive_review():
    result = build_validation_priority(
        _finding(severity="critical"),
        cve_verdict=_cve(
            "ambiguous_version_candidate",
            ambiguity=("possible_backport",),
        ),
        vulnerability_signal=_vuln(known=True),
        differential_signal="strong",
        triage_score=1.0,
    )

    assert result.band == "review"
    assert result.recommended_state == "passive_review"
    assert "version_ambiguity" in result.reasons


def test_saturated_cluster_defers_duplicate_validation():
    result = build_validation_priority(
        _finding(severity="critical"),
        cve_verdict=_cve("behaviorally_supported_cve_candidate"),
        vulnerability_signal=_vuln(known=True),
        differential_signal="strong",
        triage_score=1.0,
        duplicate_candidate=True,
        cluster_saturated=True,
    )

    assert result.band == "deferred"
    assert result.recommended_state == "defer_duplicate_validation"
    assert "cluster_validation_saturated" in result.reasons


def test_corroborated_unknown_candidate_can_be_prioritized_without_zero_day_claim():
    result = build_validation_priority(
        _finding(severity="critical"),
        cve_verdict=_cve("not_a_cve_candidate"),
        vulnerability_signal=_vuln(novel=True),
        differential_signal="strong",
        triage_score=0.8,
    )

    assert result.band in {"urgent", "high"}
    assert "corroborated_unknown_candidate" in result.reasons
    assert result.automatic_execution_authorized is False


def test_resolved_findings_never_receive_more_validation_priority():
    for status in ("confirmed", "rejected"):
        result = build_validation_priority(
            _finding(severity="critical", status=status),
            cve_verdict=_cve("behaviorally_supported_cve_candidate"),
            vulnerability_signal=_vuln(known=True),
            differential_signal="strong",
            triage_score=1.0,
        )

        assert result.band == "resolved"
        assert result.recommended_state == "no_action"
