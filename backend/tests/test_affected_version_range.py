from types import SimpleNamespace

from app.affected_version_range import (
    AFFECTED_VERSION_RANGE_SCHEMA,
    build_affected_version_range_evidence,
)


def _finding(*ranges):
    return SimpleNamespace(
        id="f1",
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
