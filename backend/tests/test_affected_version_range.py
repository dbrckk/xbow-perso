from types import SimpleNamespace

from app.affected_version_range import (
    AFFECTED_VERSION_RANGE_SCHEMA,
    build_affected_version_range_evidence,
)


def _finding(*ranges):
    return SimpleNamespace(
        id="f1",
        cve_ids=["CVE-2026-12345"],
        evidence=["cve-id:CVE-2026-12345"],
        title="fixture",
        summary="",
        affected_version_ranges=list(ranges),
    )


def test_numeric_version_inside_range_is_supported():
    result = build_affected_version_range_evidence(
        _finding(">=4.2,<4.2.16"),
        observed_versions=("4.2.12",),
    )

    assert result.schema == AFFECTED_VERSION_RANGE_SCHEMA
    assert result.state == "affected"
    assert result.matching_versions == ("4.2.12",)
    assert result.affected_version_supported is True
    assert result.exploitability_confirmed is False


def test_numeric_version_outside_range_is_not_affected():
    result = build_affected_version_range_evidence(
        _finding(">=4.2,<4.2.16"),
        observed_versions=("4.2.16",),
    )

    assert result.state == "not_affected"
    assert result.outside_versions == ("4.2.16",)
    assert result.affected_version_supported is False


def test_multiple_ranges_are_or_alternatives():
    result = build_affected_version_range_evidence(
        _finding("<4.2.16", ">=5.0,<5.1.3"),
        observed_versions=("5.1.2",),
    )

    assert result.state == "affected"
    assert result.matching_versions == ("5.1.2",)


def test_conflicting_observed_versions_are_mixed():
    result = build_affected_version_range_evidence(
        _finding("<5.1.3"),
        observed_versions=("5.1.2", "5.1.4"),
    )

    assert result.state == "mixed"
    assert result.matching_versions == ("5.1.2",)
    assert result.outside_versions == ("5.1.4",)
    assert result.affected_version_supported is False


def test_unparseable_range_stays_unknown():
    result = build_affected_version_range_evidence(
        _finding("before 5.1.3 except vendor build"),
        observed_versions=("5.1.2",),
    )

    assert result.state == "unknown"
    assert result.unparseable_ranges == (
        "before 5.1.3 except vendor build",
    )
    assert result.exploitability_confirmed is False


def test_non_numeric_observed_version_stays_unknown():
    result = build_affected_version_range_evidence(
        _finding("<5.1.3"),
        observed_versions=("5.1.2-custom",),
    )

    assert result.state == "unknown"
    assert result.matching_versions == ()
    assert result.outside_versions == ()


def test_missing_ranges_do_not_guess_applicability():
    result = build_affected_version_range_evidence(
        _finding(),
        observed_versions=("5.1.2",),
    )

    assert result.state == "not_available"
    assert result.affected_version_supported is False


def test_multiple_cves_make_shared_range_binding_unknown():
    finding = _finding("<5.1.3")
    finding.cve_ids = ["CVE-2026-1111", "CVE-2026-2222"]
    finding.evidence = [
        "cve-id:CVE-2026-1111",
        "cve-id:CVE-2026-2222",
    ]

    result = build_affected_version_range_evidence(
        finding,
        observed_versions=("5.1.4",),
    )

    assert result.state == "unknown"
    assert result.range_binding == "ambiguous_multi_cve"
    assert result.binding_ambiguity_reason == (
        "multiple_cves_share_unbound_ranges"
    )
    assert result.outside_versions == ()
    assert result.affected_version_supported is False


def test_range_without_cve_binding_is_unknown():
    finding = _finding("<5.1.3")
    finding.cve_ids = []
    finding.evidence = []
    finding.title = "generic issue"

    result = build_affected_version_range_evidence(
        finding,
        observed_versions=("5.1.2",),
    )

    assert result.state == "unknown"
    assert result.range_binding == "no_cve_binding"
    assert result.binding_ambiguity_reason == "affected_range_without_cve"


def test_unverified_range_source_cannot_become_trusted_support():
    finding = _finding(">=4.2,<4.2.16")
    finding.affected_version_range_source = "nuclei-template-metadata"
    finding.affected_version_range_verified = False

    result = build_affected_version_range_evidence(
        finding,
        observed_versions=("4.2.12",),
    )

    assert result.state == "affected"
    assert result.affected_version_supported is True
    assert result.range_source == "nuclei-template-metadata"
    assert result.range_source_verified is False
    assert result.range_provenance_state == "unverified"
    assert result.trusted_affected_version_supported is False
    assert result.exploitability_confirmed is False


def test_verified_range_source_can_support_candidate_without_confirmation():
    finding = _finding(">=4.2,<4.2.16")
    finding.affected_version_range_source = "vendor-advisory"
    finding.affected_version_range_verified = True

    result = build_affected_version_range_evidence(
        finding,
        observed_versions=("4.2.12",),
    )

    assert result.state == "affected"
    assert result.range_source == "vendor-advisory"
    assert result.range_source_verified is True
    assert result.range_provenance_state == "verified"
    assert result.trusted_affected_version_supported is True
    assert result.exploitability_confirmed is False


def test_missing_range_source_is_not_invented():
    result = build_affected_version_range_evidence(
        _finding("<5.1.3"),
        observed_versions=("5.1.2",),
    )

    assert result.range_source is None
    assert result.range_source_verified is False
    assert result.range_provenance_state == "missing"
    assert result.trusted_affected_version_supported is False
