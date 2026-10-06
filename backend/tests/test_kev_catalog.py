import pytest

from app.kev_catalog import (
    KEV_CATALOG_SCHEMA,
    KevCatalogError,
    authoritative_kev_ids,
    build_kev_catalog,
    finding_has_authoritative_kev,
)


def _document():
    return {
        "title": "CISA Known Exploited Vulnerabilities Catalog",
        "catalogVersion": "2026.10.06",
        "dateReleased": "2026-10-06T12:00:00.000Z",
        "count": 2,
        "vulnerabilities": [
            {
                "cveID": "CVE-2026-12345",
                "vendorProject": "Vendor",
                "product": "Product",
                "dateAdded": "2026-10-01",
                "dueDate": "2026-10-22",
                "knownRansomwareCampaignUse": "Known",
            },
            {
                "cveID": "CVE-2025-9999",
                "vendorProject": "Other",
                "product": "Service",
                "dateAdded": "2026-09-20",
                "dueDate": "2026-10-11",
                "knownRansomwareCampaignUse": "Unknown",
            },
        ],
    }


def test_unverified_snapshot_never_creates_authoritative_kev_claim():
    catalog = build_kev_catalog(_document(), source_verified=False)

    assert catalog.schema == KEV_CATALOG_SCHEMA
    assert catalog.source_verified is False
    assert authoritative_kev_ids(catalog) == frozenset()
    assert finding_has_authoritative_kev(
        catalog,
        ["CVE-2026-12345"],
    ) is False


def test_verified_snapshot_exposes_only_catalogued_cves_as_authoritative():
    catalog = build_kev_catalog(_document(), source_verified=True)

    assert catalog.entry_count == 2
    assert authoritative_kev_ids(catalog) == frozenset(
        {"CVE-2025-9999", "CVE-2026-12345"}
    )
    assert finding_has_authoritative_kev(
        catalog,
        ["cve-2026-12345"],
    ) is True
    assert finding_has_authoritative_kev(
        catalog,
        ["CVE-2024-1111"],
    ) is False


def test_catalog_digest_is_stable_for_same_document():
    first = build_kev_catalog(_document())
    second = build_kev_catalog(_document())

    assert len(first.source_digest_sha256) == 64
    assert first.source_digest_sha256 == second.source_digest_sha256


def test_declared_count_mismatch_fails_closed():
    document = _document()
    document["count"] = 99

    with pytest.raises(KevCatalogError, match="count"):
        build_kev_catalog(document)


def test_invalid_cve_id_fails_closed():
    document = _document()
    document["vulnerabilities"][0]["cveID"] = "not-a-cve"

    with pytest.raises(KevCatalogError, match="CVE id"):
        build_kev_catalog(document)


def test_conflicting_duplicate_cve_fails_closed():
    document = _document()
    duplicate = dict(document["vulnerabilities"][0])
    duplicate["product"] = "Different"
    document["vulnerabilities"].append(duplicate)
    document["count"] = 3

    with pytest.raises(KevCatalogError, match="conflicting duplicate"):
        build_kev_catalog(document)


def test_unsupported_source_cannot_be_treated_as_cisa_kev():
    with pytest.raises(KevCatalogError, match="unsupported"):
        build_kev_catalog(
            _document(),
            source_name="scanner-export",
            source_verified=True,
        )
