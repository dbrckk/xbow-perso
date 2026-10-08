import hashlib
import json
import os

import pytest

from app.cve_advisory_loader import (
    CveAdvisoryCatalogLoadError,
    cve_advisory_catalog_runtime_status,
    load_cve_advisory_catalog_with_status,
    load_cve_advisory_catalogs_with_status,
    load_verified_cve_advisory_catalog,
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


def _write_catalog(tmp_path):
    path = tmp_path / "cve-advisories.json"
    payload = json.dumps(
        _document(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _clear(monkeypatch):
    for name in (
        "XBOW_CVE_ADVISORY_CATALOG_PATH",
        "XBOW_CVE_ADVISORY_CATALOG_SHA256",
        "XBOW_CVE_ADVISORY_CATALOG_SOURCE",
        "XBOW_CVE_ADVISORY_CATALOG_FORMAT",
        "XBOW_CVE_ADVISORY_CATALOG_SNAPSHOT_AT",
        "XBOW_CVE_ADVISORY_NVD_PATH",
        "XBOW_CVE_ADVISORY_NVD_SHA256",
        "XBOW_CVE_ADVISORY_NVD_SNAPSHOT_AT",
        "XBOW_CVE_ADVISORY_OSV_PATH",
        "XBOW_CVE_ADVISORY_OSV_SHA256",
        "XBOW_CVE_ADVISORY_OSV_SNAPSHOT_AT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_unconfigured_loader_returns_none(monkeypatch):
    _clear(monkeypatch)

    assert load_verified_cve_advisory_catalog() is None
    assert cve_advisory_catalog_runtime_status() == {
        "configured": False,
        "available": False,
        "verified": False,
        "source_name": None,
        "source_format": "internal-v1",
        "entry_count": 0,
        "adapter": None,
        "error": None,
    }


def test_pinned_catalog_loads_as_verified(tmp_path, monkeypatch):
    _clear(monkeypatch)
    path, digest = _write_catalog(tmp_path)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_SHA256", digest)
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_SOURCE",
        "vendor-advisory-feed",
    )

    catalog, status = load_cve_advisory_catalog_with_status()

    assert catalog is not None
    assert catalog.source_verified is True
    assert catalog.source_name == "vendor-advisory-feed"
    assert catalog.entry_count == 1
    assert status == {
        "configured": True,
        "available": True,
        "verified": True,
        "source_name": "vendor-advisory-feed",
        "source_format": "internal-v1",
        "entry_count": 1,
        "adapter": None,
        "error": None,
    }


def test_digest_mismatch_fails_closed(tmp_path, monkeypatch):
    _clear(monkeypatch)
    path, _digest = _write_catalog(tmp_path)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_SHA256",
        "0" * 64,
    )

    with pytest.raises(
        CveAdvisoryCatalogLoadError,
        match="SHA-256 mismatch",
    ):
        load_verified_cve_advisory_catalog()

    catalog, status = load_cve_advisory_catalog_with_status()
    assert catalog is None
    assert status["configured"] is True
    assert status["verified"] is False
    assert status["error"] == "CVE advisory catalog SHA-256 mismatch"


def test_partial_configuration_fails_closed(tmp_path, monkeypatch):
    _clear(monkeypatch)
    path, _digest = _write_catalog(tmp_path)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))

    with pytest.raises(
        CveAdvisoryCatalogLoadError,
        match="configured together",
    ):
        load_verified_cve_advisory_catalog()


def test_malformed_json_fails_closed(tmp_path, monkeypatch):
    _clear(monkeypatch)
    path = tmp_path / "bad.json"
    payload = b"{not-json"
    path.write_bytes(payload)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_SHA256",
        hashlib.sha256(payload).hexdigest(),
    )

    with pytest.raises(
        CveAdvisoryCatalogLoadError,
        match="JSON is invalid",
    ):
        load_verified_cve_advisory_catalog()


@pytest.mark.skipif(
    not hasattr(os, "O_NOFOLLOW"),
    reason="platform lacks O_NOFOLLOW",
)
def test_symlink_catalog_is_rejected(tmp_path, monkeypatch):
    _clear(monkeypatch)
    target, digest = _write_catalog(tmp_path)
    link = tmp_path / "catalog-link.json"
    link.symlink_to(target)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(link))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_SHA256", digest)

    with pytest.raises(
        CveAdvisoryCatalogLoadError,
        match="cannot be opened",
    ):
        load_verified_cve_advisory_catalog()


def test_pinned_raw_nvd_v2_catalog_is_adapted_and_verified(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    document = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-54321",
                    "configurations": [
                        {
                            "nodes": [
                                {
                                    "operator": "OR",
                                    "negate": False,
                                    "cpeMatch": [
                                        {
                                            "vulnerable": True,
                                            "criteria": (
                                                "cpe:2.3:a:djangoproject:"
                                                "django:*:*:*:*:*:*:*:*"
                                            ),
                                            "versionStartIncluding": "5.0",
                                            "versionEndExcluding": "5.2.0",
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            }
        ]
    }
    path = tmp_path / "nvd.json"
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path.write_bytes(payload)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_SHA256",
        hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_FORMAT",
        "nvd-cve-api-v2",
    )

    catalog, status = load_cve_advisory_catalog_with_status()

    assert catalog is not None
    assert catalog.source_name == "nvd-cve-api-v2"
    assert catalog.source_verified is True
    assert catalog.entry_count == 1
    entry = catalog.entries[0]
    assert entry.cve_id == "CVE-2026-54321"
    assert entry.vendor == "djangoproject"
    assert entry.product == "django"
    assert entry.affected_version_ranges == (">=5.0,<5.2.0",)
    assert status["source_format"] == "nvd-cve-api-v2"
    assert status["adapter"] == {
        "schema": "nvd-advisory-adapter-v1",
        "input_count": 1,
        "output_count": 1,
        "skipped_complex_configurations": 0,
        "skipped_non_vulnerable_matches": 0,
        "skipped_unusable_version_matches": 0,
    }


def test_unsupported_catalog_format_fails_closed(tmp_path, monkeypatch):
    _clear(monkeypatch)
    path, digest = _write_catalog(tmp_path)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_SHA256", digest)
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_FORMAT",
        "unknown-format",
    )

    with pytest.raises(
        CveAdvisoryCatalogLoadError,
        match="format is unsupported",
    ):
        load_verified_cve_advisory_catalog()


def test_pinned_raw_osv_catalog_is_adapted_and_verified(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    document = {
        "id": "GHSA-fixture",
        "aliases": ["CVE-2026-65432"],
        "affected": [
            {
                "package": {
                    "ecosystem": "PyPI",
                    "name": "Django",
                },
                "ranges": [
                    {
                        "type": "SEMVER",
                        "events": [
                            {"introduced": "5.0.0"},
                            {"fixed": "5.2.0"},
                        ],
                    }
                ],
                "versions": [],
            }
        ],
    }
    path = tmp_path / "osv.json"
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path.write_bytes(payload)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_SHA256",
        hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_FORMAT",
        "osv-v1",
    )

    catalog, status = load_cve_advisory_catalog_with_status()

    assert catalog is not None
    assert catalog.source_name == "osv-v1"
    assert catalog.source_verified is True
    assert catalog.entry_count == 1
    entry = catalog.entries[0]
    assert entry.cve_id == "CVE-2026-65432"
    assert entry.identity_kind == "package"
    assert entry.package_ecosystem == "pypi"
    assert entry.package_name == "Django"
    assert entry.affected_version_ranges == (">=5.0.0,<5.2.0",)
    assert status["source_format"] == "osv-v1"
    assert status["adapter"] == {
        "schema": "osv-advisory-adapter-v1",
        "input_count": 1,
        "output_count": 1,
        "skipped_ambiguous_cve_bindings": 0,
        "skipped_non_semver_ranges": 0,
        "skipped_unusable_semver_ranges": 0,
        "skipped_unusable_explicit_versions": 0,
    }


def test_osv_adapter_diagnostics_expose_skip_counts_without_identifiers(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    document = {
        "id": "GHSA-private-marker",
        "aliases": ["CVE-2026-70001"],
        "affected": [
            {
                "package": {
                    "ecosystem": "PyPI",
                    "name": "PrivatePackageMarker",
                },
                "ranges": [
                    {
                        "type": "ECOSYSTEM",
                        "events": [
                            {"introduced": "1.0-r0"},
                            {"fixed": "2.0-r1"},
                        ],
                    }
                ],
                "versions": [],
            }
        ],
    }
    path = tmp_path / "osv-skipped.json"
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path.write_bytes(payload)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_SHA256",
        hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_FORMAT", "osv-v1")

    catalog, status = load_cve_advisory_catalog_with_status()

    assert catalog is not None
    assert catalog.entry_count == 0
    assert status["adapter"]["input_count"] == 1
    assert status["adapter"]["output_count"] == 0
    assert status["adapter"]["skipped_non_semver_ranges"] == 1
    rendered = str(status)
    assert "GHSA-private-marker" not in rendered
    assert "CVE-2026-70001" not in rendered
    assert "PrivatePackageMarker" not in rendered


def _write_json(tmp_path, name, document):
    path = tmp_path / name
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    path.write_bytes(payload)
    return path, hashlib.sha256(payload).hexdigest()


def _nvd_document():
    return {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-54321",
                    "configurations": [
                        {
                            "nodes": [
                                {
                                    "operator": "OR",
                                    "negate": False,
                                    "cpeMatch": [
                                        {
                                            "vulnerable": True,
                                            "criteria": (
                                                "cpe:2.3:a:djangoproject:"
                                                "django:*:*:*:*:*:*:*:*"
                                            ),
                                            "versionStartIncluding": "5.0",
                                            "versionEndExcluding": "5.2.0",
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            }
        ]
    }


def _osv_document():
    return {
        "id": "GHSA-multisource-fixture",
        "aliases": ["CVE-2026-54321"],
        "affected": [
            {
                "package": {
                    "ecosystem": "PyPI",
                    "name": "Django",
                },
                "ranges": [
                    {
                        "type": "SEMVER",
                        "events": [
                            {"introduced": "5.0.0"},
                            {"fixed": "5.2.0"},
                        ],
                    }
                ],
                "versions": [],
            }
        ],
    }


def test_independently_pinned_nvd_and_osv_load_together(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    nvd_path, nvd_digest = _write_json(
        tmp_path,
        "nvd-multi.json",
        _nvd_document(),
    )
    osv_path, osv_digest = _write_json(
        tmp_path,
        "osv-multi.json",
        _osv_document(),
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_PATH", str(nvd_path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_SHA256", nvd_digest)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_OSV_PATH", str(osv_path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_OSV_SHA256", osv_digest)

    catalogs, status = load_cve_advisory_catalogs_with_status()

    assert tuple(item.source_name for item in catalogs) == (
        "nvd-cve-api-v2",
        "osv-v1",
    )
    assert tuple(item.source_verified for item in catalogs) == (
        True,
        True,
    )
    assert status["schema"] == "cve-advisory-source-set-v1"
    assert status["configured"] is True
    assert status["available"] is True
    assert status["verified"] is True
    assert status["configured_source_count"] == 2
    assert status["available_source_count"] == 2
    assert status["invalid_source_count"] == 0
    assert status["error"] is None
    by_kind = {
        item["source_kind"]: item
        for item in status["sources"]
    }
    assert by_kind["nvd"]["entry_count"] == 1
    assert by_kind["nvd"]["verified"] is True
    assert by_kind["osv"]["entry_count"] == 1
    assert by_kind["osv"]["verified"] is True
    assert by_kind["legacy"]["configured"] is False


def test_invalid_osv_does_not_disable_valid_nvd_but_marks_set_degraded(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    nvd_path, nvd_digest = _write_json(
        tmp_path,
        "nvd-valid.json",
        _nvd_document(),
    )
    osv_path, _osv_digest = _write_json(
        tmp_path,
        "osv-invalid-pin.json",
        _osv_document(),
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_PATH", str(nvd_path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_SHA256", nvd_digest)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_OSV_PATH", str(osv_path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_OSV_SHA256", "0" * 64)

    catalogs, status = load_cve_advisory_catalogs_with_status()

    assert tuple(item.source_name for item in catalogs) == (
        "nvd-cve-api-v2",
    )
    assert status["available"] is True
    assert status["verified"] is False
    assert status["configured_source_count"] == 2
    assert status["available_source_count"] == 1
    assert status["invalid_source_count"] == 1
    assert status["error"] == "one_or_more_advisory_sources_invalid"
    rendered = str(status)
    assert str(osv_path) not in rendered
    assert "SHA-256 mismatch" in rendered


def test_named_sources_expose_stable_authorities(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    nvd_path, nvd_digest = _write_json(
        tmp_path,
        "nvd-authority.json",
        _nvd_document(),
    )
    osv_path, osv_digest = _write_json(
        tmp_path,
        "osv-authority.json",
        _osv_document(),
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_PATH", str(nvd_path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_SHA256", nvd_digest)
    monkeypatch.setenv("XBOW_CVE_ADVISORY_OSV_PATH", str(osv_path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_OSV_SHA256", osv_digest)

    catalogs, status = load_cve_advisory_catalogs_with_status()

    assert tuple(item.source_authority for item in catalogs) == (
        "nvd",
        "osv",
    )
    by_kind = {
        item["source_kind"]: item
        for item in status["sources"]
    }
    assert by_kind["nvd"]["source_authority"] == "nvd"
    assert by_kind["osv"]["source_authority"] == "osv"


def test_legacy_nvd_alias_and_named_nvd_same_snapshot_are_deduplicated(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    path, digest = _write_json(
        tmp_path,
        "nvd-shared.json",
        _nvd_document(),
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_PATH", str(path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_CATALOG_SHA256", digest)
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_FORMAT",
        "nvd-cve-api-v2",
    )
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_CATALOG_SOURCE",
        "nvd-local-alias",
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_PATH", str(path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_SHA256", digest)

    catalogs, status = load_cve_advisory_catalogs_with_status()

    assert len(catalogs) == 1
    assert catalogs[0].source_authority == "nvd"
    assert status["configured_source_count"] == 2
    assert status["available_source_count"] == 1
    assert status["invalid_source_count"] == 0


def test_nvd_top_level_timestamp_becomes_catalog_snapshot(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    document = _nvd_document()
    document["timestamp"] = "2026-10-08T07:45:00.000Z"
    path, digest = _write_json(
        tmp_path,
        "nvd-with-timestamp.json",
        document,
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_PATH", str(path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_SHA256", digest)

    catalogs, _status = load_cve_advisory_catalogs_with_status()

    assert len(catalogs) == 1
    assert catalogs[0].source_authority == "nvd"
    assert catalogs[0].source_snapshot_at == (
        "2026-10-08T07:45:00+00:00"
    )


def test_explicit_osv_snapshot_timestamp_is_preserved(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    path, digest = _write_json(
        tmp_path,
        "osv-with-snapshot.json",
        _osv_document(),
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_OSV_PATH", str(path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_OSV_SHA256", digest)
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_OSV_SNAPSHOT_AT",
        "2026-10-08T08:00:00+00:00",
    )

    catalogs, _status = load_cve_advisory_catalogs_with_status()

    assert len(catalogs) == 1
    assert catalogs[0].source_authority == "osv"
    assert catalogs[0].source_snapshot_at == (
        "2026-10-08T08:00:00+00:00"
    )


def test_invalid_explicit_snapshot_timestamp_fails_source_closed(
    tmp_path,
    monkeypatch,
):
    _clear(monkeypatch)
    path, digest = _write_json(
        tmp_path,
        "nvd-invalid-snapshot.json",
        _nvd_document(),
    )
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_PATH", str(path))
    monkeypatch.setenv("XBOW_CVE_ADVISORY_NVD_SHA256", digest)
    monkeypatch.setenv(
        "XBOW_CVE_ADVISORY_NVD_SNAPSHOT_AT",
        "not-a-timestamp",
    )

    catalogs, status = load_cve_advisory_catalogs_with_status()

    assert catalogs == ()
    assert status["invalid_source_count"] == 1
    assert status["available"] is False
    assert status["verified"] is False
