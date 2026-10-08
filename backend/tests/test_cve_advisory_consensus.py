from datetime import datetime, timezone
from types import SimpleNamespace

from app.cve_advisory_catalog import build_cve_advisory_catalog
from app.cve_advisory_consensus import (
    CVE_ADVISORY_CONSENSUS_SCHEMA,
    build_cve_advisory_consensus,
)


def _finding():
    return SimpleNamespace(
        id="f1",
        cve_ids=["CVE-2026-12345"],
        evidence=["cve-id:CVE-2026-12345"],
        title="fixture",
        summary="",
        vendor="djangoproject",
        product="django",
        package_ecosystem="PyPI",
        package_name="Django",
        package_version="5.1.4",
    )


def _catalog(
    source_name,
    entry,
    *,
    source_authority=None,
    source_snapshot_at=None,
):
    return build_cve_advisory_catalog(
        {"count": 1, "entries": [entry]},
        source_name=source_name,
        source_authority=source_authority,
        source_verified=True,
        source_snapshot_at=source_snapshot_at,
    )


def test_parallel_cpe_and_package_identities_are_not_auto_merged():
    nvd = _catalog(
        "nvd-cve-api-v2",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
    )
    osv = _catalog(
        "osv-v1",
        {
            "cve_id": "CVE-2026-12345",
            "package_ecosystem": "PyPI",
            "package_name": "Django",
            "affected_version_ranges": ["<5.2.0"],
        },
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (nvd, osv),
        fingerprint_versions=("5.1.4",),
        package_version="5.1.4",
    )

    assert result.schema == CVE_ADVISORY_CONSENSUS_SCHEMA
    assert result.state == "parallel_unbound_identities"
    assert result.identity_count == 2
    assert result.identity_kinds == ("cpe", "package")
    assert result.cross_source_agreement is False
    assert result.ambiguity_reasons == (
        "parallel_unbound_advisory_identities",
    )
    assert result.exploitability_confirmed is False


def test_exact_identity_sources_can_agree_on_applicability():
    first = _catalog(
        "source-a",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
    )
    second = _catalog(
        "source-b",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": [">=5.0,<5.2.0"],
        },
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (first, second),
        fingerprint_versions=("5.1.4",),
    )

    assert result.state == "exact_identity_applicability_agreement"
    assert result.source_count == 2
    assert result.identity_count == 1
    assert result.cross_source_agreement is True
    assert result.agreed_applicability_state == "affected"
    assert result.range_sets_equal is False
    assert result.ambiguity_reasons == ()


def test_exact_identity_applicability_conflict_is_ambiguous():
    fixed = _catalog(
        "source-fixed",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.1.3"],
        },
    )
    affected = _catalog(
        "source-affected",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": [">=5.1,<5.2.0"],
        },
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (fixed, affected),
        fingerprint_versions=("5.1.4",),
    )

    assert result.state == "exact_identity_applicability_conflict"
    assert result.cross_source_agreement is False
    assert result.ambiguity_reasons == (
        "cross_source_advisory_applicability_conflict",
    )
    assert {
        item.applicability_state for item in result.evidence
    } == {"affected", "not_affected"}


def test_unverified_catalog_is_ignored_by_consensus():
    verified = _catalog(
        "verified",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
    )
    unverified = build_cve_advisory_catalog(
        {
            "count": 1,
            "entries": [
                {
                    "cve_id": "CVE-2026-12345",
                    "vendor": "djangoproject",
                    "product": "django",
                    "affected_version_ranges": ["<5.1.0"],
                }
            ],
        },
        source_name="unverified",
        source_verified=False,
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (verified, unverified),
        fingerprint_versions=("5.1.4",),
    )

    assert result.state == "single_source"
    assert result.source_count == 1
    assert result.matched_advisory_count == 1
    assert result.sources == ("verified",)


def test_same_authority_aliases_do_not_create_cross_source_agreement():
    first = _catalog(
        "nvd-primary",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
        source_authority="nvd",
    )
    second = _catalog(
        "nvd-mirror",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
        source_authority="nvd",
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (first, second),
        fingerprint_versions=("5.1.4",),
    )

    assert result.state == "single_source"
    assert result.source_count == 1
    assert result.source_instance_count == 2
    assert result.authorities == ("nvd",)
    assert result.cross_source_agreement is False
    assert result.ambiguity_reasons == ()


def test_same_authority_conflicting_snapshots_are_ambiguous():
    old_snapshot = _catalog(
        "nvd-2026-10-01",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.1.3"],
        },
        source_authority="nvd",
    )
    new_snapshot = _catalog(
        "nvd-2026-10-08",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": [">=5.1,<5.2.0"],
        },
        source_authority="nvd",
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (old_snapshot, new_snapshot),
        fingerprint_versions=("5.1.4",),
    )

    assert result.state == "same_authority_snapshot_conflict"
    assert result.source_count == 1
    assert result.source_instance_count == 2
    assert result.cross_source_agreement is False
    assert result.ambiguity_reasons == (
        "same_authority_advisory_snapshot_conflict",
    )
    assert {
        item.applicability_state for item in result.evidence
    } == {"affected", "not_affected"}


def test_distinct_authorities_can_still_form_exact_identity_consensus():
    nvd = _catalog(
        "feed-a",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
        source_authority="nvd",
    )
    vendor = _catalog(
        "feed-b",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": [">=5.0,<5.2.0"],
        },
        source_authority="vendor",
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (nvd, vendor),
        fingerprint_versions=("5.1.4",),
    )

    assert result.state == "exact_identity_applicability_agreement"
    assert result.source_count == 2
    assert result.source_instance_count == 2
    assert result.authorities == ("nvd", "vendor")
    assert result.cross_source_agreement is True


def test_exact_identity_sources_agreeing_not_affected_downgrade_candidate():
    first = _catalog(
        "source-a",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.1.3"],
        },
        source_authority="nvd",
    )
    second = _catalog(
        "source-b",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.1.4"],
        },
        source_authority="vendor",
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (first, second),
        fingerprint_versions=("5.1.4",),
    )

    assert result.state == "exact_identity_applicability_agreement"
    assert result.cross_source_agreement is True
    assert result.agreed_applicability_state == "not_affected"
    assert result.ambiguity_reasons == (
        "cross_source_advisory_not_affected",
    )
    assert {
        item.applicability_state for item in result.evidence
    } == {"not_affected"}
    assert result.exploitability_confirmed is False


def test_stale_advisory_source_cannot_form_cross_source_agreement():
    stale = _catalog(
        "nvd",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
        source_authority="nvd",
        source_snapshot_at="2026-08-01T00:00:00+00:00",
    )
    fresh = _catalog(
        "vendor",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": [">=5.0,<5.2.0"],
        },
        source_authority="vendor",
        source_snapshot_at="2026-10-07T00:00:00+00:00",
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (stale, fresh),
        fingerprint_versions=("5.1.4",),
        now=datetime(2026, 10, 8, tzinfo=timezone.utc),
        max_source_age_days=30,
    )

    assert result.state == "stale_source_evidence"
    assert result.cross_source_agreement is False
    assert result.agreed_applicability_state is None
    assert result.stale_source_count == 1
    assert result.unknown_freshness_source_count == 0
    assert "stale_advisory_source" in result.ambiguity_reasons
    by_source = {
        item.source_name: item
        for item in result.evidence
    }
    assert by_source["nvd"].source_freshness == "stale"
    assert by_source["vendor"].source_freshness == "fresh"


def test_unknown_snapshot_age_does_not_invent_staleness():
    first = _catalog(
        "source-a",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
        source_authority="a",
    )
    second = _catalog(
        "source-b",
        {
            "cve_id": "CVE-2026-12345",
            "vendor": "djangoproject",
            "product": "django",
            "affected_version_ranges": ["<5.2.0"],
        },
        source_authority="b",
    )

    result = build_cve_advisory_consensus(
        _finding(),
        (first, second),
        fingerprint_versions=("5.1.4",),
        now=datetime(2026, 10, 8, tzinfo=timezone.utc),
    )

    assert result.state == "exact_identity_applicability_agreement"
    assert result.cross_source_agreement is True
    assert result.stale_source_count == 0
    assert result.unknown_freshness_source_count == 2
    assert "stale_advisory_source" not in result.ambiguity_reasons
