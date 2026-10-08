import pytest

from app.cve_advisory_catalog import (
    CVE_ADVISORY_CATALOG_SCHEMA,
    CveAdvisoryCatalogError,
    build_cve_advisory_catalog,
    find_verified_cve_advisories,
    find_verified_cve_advisory,
)


def _document():
    return {
        "count": 1,
        "entries": [
            {
                "cve_id": "CVE-2026-12345",
                "vendor": "djangoproject",
                "product": "django",
                "affected_version_ranges": [">=5.0,<5.2.0"],
            }
        ],
    }


def test_verified_catalog_exposes_authoritative_entry():
    catalog = build_cve_advisory_catalog(
        _document(),
        source_name="vendor-advisory-feed",
        source_verified=True,
    )

    assert catalog.schema == CVE_ADVISORY_CATALOG_SCHEMA
    assert catalog.source_verified is True
    assert catalog.entry_count == 1
    assert len(catalog.source_digest_sha256) == 64

    entry = find_verified_cve_advisory(
        catalog,
        cve_id="CVE-2026-12345",
        vendor="djangoproject",
        product="django",
    )

    assert entry is not None
    assert entry.identity_kind == "cpe"
    assert entry.authoritative is True
    assert entry.affected_version_ranges == (">=5.0,<5.2.0",)


def test_unverified_catalog_never_returns_trusted_advisory():
    catalog = build_cve_advisory_catalog(
        _document(),
        source_name="scanner-cache",
        source_verified=False,
    )

    assert find_verified_cve_advisory(
        catalog,
        cve_id="CVE-2026-12345",
        vendor="djangoproject",
        product="django",
    ) is None


def test_ambiguous_same_cve_without_product_binding_fails_closed():
    document = {
        "count": 2,
        "entries": [
            {
                "cve_id": "CVE-2026-12345",
                "vendor": "vendor-a",
                "product": "product-a",
                "affected_version_ranges": ["<2.0"],
            },
            {
                "cve_id": "CVE-2026-12345",
                "vendor": "vendor-b",
                "product": "product-b",
                "affected_version_ranges": ["<3.0"],
            },
        ],
    }
    catalog = build_cve_advisory_catalog(
        document,
        source_name="verified-feed",
        source_verified=True,
    )

    assert find_verified_cve_advisory(
        catalog,
        cve_id="CVE-2026-12345",
    ) is None


def test_conflicting_duplicate_advisory_entry_is_rejected():
    document = {
        "count": 2,
        "entries": [
            {
                "cve_id": "CVE-2026-12345",
                "vendor": "vendor",
                "product": "product",
                "affected_version_ranges": ["<2.0"],
            },
            {
                "cve_id": "CVE-2026-12345",
                "vendor": "vendor",
                "product": "product",
                "affected_version_ranges": ["<3.0"],
            },
        ],
    }

    with pytest.raises(
        CveAdvisoryCatalogError,
        match="conflicting duplicate",
    ):
        build_cve_advisory_catalog(
            document,
            source_name="verified-feed",
            source_verified=True,
        )


def test_invalid_lookup_identity_fails_closed():
    catalog = build_cve_advisory_catalog(
        _document(),
        source_name="verified-feed",
        source_verified=True,
    )

    assert find_verified_cve_advisory(
        catalog,
        cve_id="not-a-cve",
        product="django",
    ) is None


def test_verified_package_advisory_matches_ecosystem_and_name():
    document = {
        "count": 1,
        "entries": [
            {
                "cve_id": "CVE-2026-22222",
                "package_ecosystem": "PyPI",
                "package_name": "Django",
                "affected_version_ranges": ["<5.2.1"],
            }
        ],
    }
    catalog = build_cve_advisory_catalog(
        document,
        source_name="osv-fixture",
        source_verified=True,
    )

    entry = find_verified_cve_advisory(
        catalog,
        cve_id="CVE-2026-22222",
        package_ecosystem="pypi",
        package_name="Django",
    )

    assert entry is not None
    assert entry.identity_kind == "package"
    assert entry.vendor is None
    assert entry.product is None
    assert entry.package_ecosystem == "pypi"
    assert entry.package_name == "Django"


def test_package_name_matching_is_conservative_and_case_sensitive():
    catalog = build_cve_advisory_catalog(
        {
            "count": 1,
            "entries": [
                {
                    "cve_id": "CVE-2026-22222",
                    "package_ecosystem": "PyPI",
                    "package_name": "Django",
                    "affected_version_ranges": ["<5.2.1"],
                }
            ],
        },
        source_name="osv-fixture",
        source_verified=True,
    )

    assert find_verified_cve_advisory(
        catalog,
        cve_id="CVE-2026-22222",
        package_ecosystem="pypi",
        package_name="django",
    ) is None


@pytest.mark.parametrize(
    "entry",
    (
        {
            "cve_id": "CVE-2026-33333",
            "package_ecosystem": "PyPI",
            "affected_version_ranges": ["<2.0"],
        },
        {
            "cve_id": "CVE-2026-33333",
            "package_name": "fixture",
            "affected_version_ranges": ["<2.0"],
        },
        {
            "cve_id": "CVE-2026-33333",
            "vendor": "vendor",
            "product": "product",
            "package_ecosystem": "PyPI",
            "package_name": "fixture",
            "affected_version_ranges": ["<2.0"],
        },
        {
            "cve_id": "CVE-2026-33333",
            "affected_version_ranges": ["<2.0"],
        },
    ),
)
def test_advisory_identity_must_be_exactly_one_complete_kind(entry):
    with pytest.raises(CveAdvisoryCatalogError):
        build_cve_advisory_catalog(
            {"count": 1, "entries": [entry]},
            source_name="fixture",
            source_verified=True,
        )


def test_plural_lookup_preserves_exact_cpe_and_package_matches():
    catalog = build_cve_advisory_catalog(
        {
            "count": 2,
            "entries": [
                {
                    "cve_id": "CVE-2026-55555",
                    "vendor": "djangoproject",
                    "product": "django",
                    "affected_version_ranges": ["<5.2.0"],
                },
                {
                    "cve_id": "CVE-2026-55555",
                    "package_ecosystem": "PyPI",
                    "package_name": "Django",
                    "affected_version_ranges": ["<5.2.0"],
                },
            ],
        },
        source_name="combined-fixture",
        source_verified=True,
    )

    matches = find_verified_cve_advisories(
        catalog,
        cve_id="CVE-2026-55555",
        vendor="djangoproject",
        product="django",
        package_ecosystem="pypi",
        package_name="Django",
    )

    assert tuple(item.identity_kind for item in matches) == (
        "cpe",
        "package",
    )
    assert find_verified_cve_advisory(
        catalog,
        cve_id="CVE-2026-55555",
        vendor="djangoproject",
        product="django",
        package_ecosystem="pypi",
        package_name="Django",
    ) is None


def test_source_authority_defaults_to_source_name():
    catalog = build_cve_advisory_catalog(
        _document(),
        source_name="vendor-advisory-feed",
        source_verified=True,
    )

    assert catalog.source_authority == "vendor-advisory-feed"


def test_explicit_source_authority_is_normalized_and_persisted():
    catalog = build_cve_advisory_catalog(
        _document(),
        source_name="NVD Mirror Label",
        source_authority="NVD",
        source_verified=True,
    )

    assert catalog.source_name == "NVD Mirror Label"
    assert catalog.source_authority == "nvd"
    assert catalog.to_dict()["source_authority"] == "nvd"


def test_catalog_normalizes_source_snapshot_to_utc():
    catalog = build_cve_advisory_catalog(
        _document(),
        source_name="fixture",
        source_verified=True,
        source_snapshot_at="2026-10-08T09:30:00+02:00",
    )

    assert catalog.source_snapshot_at == "2026-10-08T07:30:00+00:00"


def test_catalog_rejects_naive_source_snapshot_timestamp():
    with pytest.raises(
        CveAdvisoryCatalogError,
        match="must include a timezone",
    ):
        build_cve_advisory_catalog(
            _document(),
            source_name="fixture",
            source_verified=True,
            source_snapshot_at="2026-10-08T09:30:00",
        )
