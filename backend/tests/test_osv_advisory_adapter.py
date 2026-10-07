import pytest

from app.osv_advisory_adapter import (
    OSV_ADVISORY_ADAPTER_SCHEMA,
    OsvAdvisoryAdapterError,
    adapt_osv_v1,
)


def _record(*, vuln_id="CVE-2026-12345", aliases=None, affected=None):
    return {
        "id": vuln_id,
        "aliases": list(aliases or []),
        "affected": list(affected or []),
    }


def _affected(
    *,
    ecosystem="PyPI",
    name="Django",
    ranges=None,
    versions=None,
):
    return {
        "package": {
            "ecosystem": ecosystem,
            "name": name,
        },
        "ranges": list(ranges or []),
        "versions": list(versions or []),
    }


def _range(range_type, *events):
    return {
        "type": range_type,
        "events": list(events),
    }


def test_semver_range_is_converted_to_package_advisory():
    result = adapt_osv_v1(
        _record(
            affected=[
                _affected(
                    ranges=[
                        _range(
                            "SEMVER",
                            {"introduced": "5.0.0"},
                            {"fixed": "5.2.0"},
                        )
                    ]
                )
            ]
        )
    )

    assert result.schema == OSV_ADVISORY_ADAPTER_SCHEMA
    assert result.output_entry_count == 1
    assert result.document == {
        "count": 1,
        "entries": [
            {
                "cve_id": "CVE-2026-12345",
                "package_ecosystem": "pypi",
                "package_name": "Django",
                "affected_version_ranges": [">=5.0.0,<5.2.0"],
            }
        ],
    }


def test_introduced_zero_and_fixed_becomes_bounded_from_zero():
    result = adapt_osv_v1(
        _record(
            affected=[
                _affected(
                    ranges=[
                        _range(
                            "SEMVER",
                            {"introduced": "0"},
                            {"fixed": "2.0.0"},
                        )
                    ]
                )
            ]
        )
    )

    assert result.document["entries"][0]["affected_version_ranges"] == [
        ">=0,<2.0.0"
    ]


def test_multiple_semver_intervals_are_preserved():
    result = adapt_osv_v1(
        _record(
            affected=[
                _affected(
                    ranges=[
                        _range(
                            "SEMVER",
                            {"introduced": "1.0.0"},
                            {"fixed": "1.2.0"},
                            {"introduced": "2.0.0"},
                            {"last_affected": "2.1.4"},
                        )
                    ]
                )
            ]
        )
    )

    assert result.document["entries"][0]["affected_version_ranges"] == [
        ">=1.0.0,<1.2.0",
        ">=2.0.0,<=2.1.4",
    ]


def test_non_semver_range_is_not_generically_ordered():
    result = adapt_osv_v1(
        _record(
            affected=[
                _affected(
                    ranges=[
                        _range(
                            "ECOSYSTEM",
                            {"introduced": "1.0-r0"},
                            {"fixed": "2.0-r1"},
                        )
                    ]
                )
            ]
        )
    )

    assert result.output_entry_count == 0
    assert result.skipped_non_semver_ranges == 1


def test_explicit_numeric_versions_are_safe_exact_matches():
    result = adapt_osv_v1(
        _record(
            affected=[
                _affected(
                    ranges=[
                        _range(
                            "GIT",
                            {"introduced": "a" * 40},
                            {"fixed": "b" * 40},
                        )
                    ],
                    versions=["1.2.3", "1.2.4"],
                )
            ]
        )
    )

    assert result.skipped_non_semver_ranges == 1
    assert result.document["entries"][0]["affected_version_ranges"] == [
        "=1.2.3",
        "=1.2.4",
    ]


def test_non_numeric_semver_is_left_unknown():
    result = adapt_osv_v1(
        _record(
            affected=[
                _affected(
                    ranges=[
                        _range(
                            "SEMVER",
                            {"introduced": "1.2.3-beta.1"},
                            {"fixed": "1.2.4"},
                        )
                    ]
                )
            ]
        )
    )

    assert result.output_entry_count == 0
    assert result.skipped_unusable_semver_ranges == 1


def test_multiple_cve_aliases_make_binding_ambiguous():
    result = adapt_osv_v1(
        _record(
            vuln_id="GHSA-fixture",
            aliases=["CVE-2026-11111", "CVE-2026-22222"],
            affected=[
                _affected(
                    versions=["1.2.3"],
                )
            ],
        )
    )

    assert result.output_entry_count == 0
    assert result.skipped_ambiguous_cve_bindings == 1


def test_single_cve_alias_binds_non_cve_osv_id():
    result = adapt_osv_v1(
        _record(
            vuln_id="GHSA-fixture",
            aliases=["CVE-2026-11111", "GHSA-other"],
            affected=[_affected(versions=["1.2.3"])],
        )
    )

    assert result.document["entries"][0]["cve_id"] == "CVE-2026-11111"


def test_event_with_multiple_state_keys_is_rejected_conservatively():
    result = adapt_osv_v1(
        _record(
            affected=[
                _affected(
                    ranges=[
                        _range(
                            "SEMVER",
                            {
                                "introduced": "1.0.0",
                                "fixed": "1.1.0",
                            },
                        )
                    ]
                )
            ]
        )
    )

    assert result.output_entry_count == 0
    assert result.skipped_unusable_semver_ranges == 1


def test_invalid_package_identity_is_rejected():
    with pytest.raises(
        OsvAdvisoryAdapterError,
        match="package name",
    ):
        adapt_osv_v1(
            _record(
                affected=[
                    {
                        "package": {
                            "ecosystem": "PyPI",
                            "name": "",
                        },
                        "ranges": [],
                        "versions": ["1.2.3"],
                    }
                ]
            )
        )
