import pytest

from app.cve_advisory_catalog import (
    CVE_ADVISORY_CATALOG_SCHEMA,
    CveAdvisoryCatalogError,
    build_cve_advisory_catalog,
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
