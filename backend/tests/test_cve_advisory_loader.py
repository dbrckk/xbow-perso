import hashlib
import json
import os

import pytest

from app.cve_advisory_loader import (
    CveAdvisoryCatalogLoadError,
    cve_advisory_catalog_runtime_status,
    load_cve_advisory_catalog_with_status,
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
        "entry_count": 0,
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
        "entry_count": 1,
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
