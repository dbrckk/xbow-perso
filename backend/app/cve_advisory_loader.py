from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from .cve_advisory_catalog import (
    CveAdvisoryCatalog,
    CveAdvisoryCatalogError,
    build_cve_advisory_catalog,
)
from .nvd_advisory_adapter import (
    NvdAdvisoryAdapterError,
    adapt_nvd_cve_api_v2,
)
from .osv_advisory_adapter import (
    OsvAdvisoryAdapterError,
    adapt_osv_v1,
)


_MAX_CATALOG_BYTES = 8 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_ENV = "XBOW_CVE_ADVISORY_CATALOG_PATH"
_SHA_ENV = "XBOW_CVE_ADVISORY_CATALOG_SHA256"
_SOURCE_ENV = "XBOW_CVE_ADVISORY_CATALOG_SOURCE"
_FORMAT_ENV = "XBOW_CVE_ADVISORY_CATALOG_FORMAT"
_ALLOWED_FORMATS = frozenset(
    {"internal-v1", "nvd-cve-api-v2", "osv-v1"}
)


class CveAdvisoryCatalogLoadError(RuntimeError):
    pass


def _read_regular_file(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog cannot be opened"
        ) from exc

    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise CveAdvisoryCatalogLoadError(
                "CVE advisory catalog must be a regular file"
            )
        if info.st_size < 2 or info.st_size > _MAX_CATALOG_BYTES:
            raise CveAdvisoryCatalogLoadError(
                "CVE advisory catalog size is invalid"
            )
        with os.fdopen(fd, "rb", closefd=False) as handle:
            payload = handle.read(_MAX_CATALOG_BYTES + 1)
        if len(payload) > _MAX_CATALOG_BYTES:
            raise CveAdvisoryCatalogLoadError(
                "CVE advisory catalog exceeds byte limit"
            )
        return payload
    finally:
        os.close(fd)


def _adapter_diagnostics(source_format: str, adapted: Any) -> dict[str, Any] | None:
    if source_format == "nvd-cve-api-v2":
        return {
            "schema": adapted.schema,
            "input_count": adapted.input_vulnerability_count,
            "output_count": adapted.output_entry_count,
            "skipped_complex_configurations": (
                adapted.skipped_complex_configurations
            ),
            "skipped_non_vulnerable_matches": (
                adapted.skipped_non_vulnerable_matches
            ),
            "skipped_unusable_version_matches": (
                adapted.skipped_unusable_version_matches
            ),
        }
    if source_format == "osv-v1":
        return {
            "schema": adapted.schema,
            "input_count": adapted.input_record_count,
            "output_count": adapted.output_entry_count,
            "skipped_ambiguous_cve_bindings": (
                adapted.skipped_ambiguous_cve_bindings
            ),
            "skipped_non_semver_ranges": adapted.skipped_non_semver_ranges,
            "skipped_unusable_semver_ranges": (
                adapted.skipped_unusable_semver_ranges
            ),
            "skipped_unusable_explicit_versions": (
                adapted.skipped_unusable_explicit_versions
            ),
        }
    return None


def _load_verified_cve_advisory_catalog_with_diagnostics(
) -> tuple[CveAdvisoryCatalog | None, dict[str, Any] | None]:
    path_raw = os.getenv(_PATH_ENV, "").strip()
    digest_raw = os.getenv(_SHA_ENV, "").strip().lower()

    if not path_raw and not digest_raw:
        return None, None
    if not path_raw or not digest_raw:
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog path and SHA-256 must be configured together"
        )
    if not _SHA256_RE.fullmatch(digest_raw):
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog SHA-256 is invalid"
        )

    payload = _read_regular_file(Path(path_raw))
    actual_digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_digest, digest_raw):
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog SHA-256 mismatch"
        )

    try:
        document: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog JSON is invalid"
        ) from exc
    if not isinstance(document, dict):
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog root must be an object"
        )

    source_format = os.getenv(
        _FORMAT_ENV,
        "internal-v1",
    ).strip().lower()
    if source_format not in _ALLOWED_FORMATS:
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog format is unsupported"
        )

    adapter_diagnostics: dict[str, Any] | None = None
    if source_format == "nvd-cve-api-v2":
        try:
            adapted = adapt_nvd_cve_api_v2(document)
        except NvdAdvisoryAdapterError as exc:
            raise CveAdvisoryCatalogLoadError(
                "NVD advisory catalog adaptation failed"
            ) from exc
        adapter_diagnostics = _adapter_diagnostics(source_format, adapted)
        document = adapted.document

    if source_format == "osv-v1":
        try:
            adapted = adapt_osv_v1(document)
        except OsvAdvisoryAdapterError as exc:
            raise CveAdvisoryCatalogLoadError(
                "OSV advisory catalog adaptation failed"
            ) from exc
        adapter_diagnostics = _adapter_diagnostics(source_format, adapted)
        document = adapted.document

    default_source_name = {
        "nvd-cve-api-v2": "nvd-cve-api-v2",
        "osv-v1": "osv-v1",
    }.get(source_format, "pinned-cve-advisory-file")
    source_name = os.getenv(
        _SOURCE_ENV,
        default_source_name,
    ).strip()
    try:
        catalog = build_cve_advisory_catalog(
            document,
            source_name=source_name,
            source_verified=True,
        )
    except CveAdvisoryCatalogError as exc:
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog schema validation failed"
        ) from exc
    return catalog, adapter_diagnostics


def load_verified_cve_advisory_catalog() -> CveAdvisoryCatalog | None:
    catalog, _adapter_diagnostics_value = (
        _load_verified_cve_advisory_catalog_with_diagnostics()
    )
    return catalog


def load_cve_advisory_catalog_with_status(
) -> tuple[CveAdvisoryCatalog | None, dict[str, Any]]:
    configured = bool(
        os.getenv(_PATH_ENV, "").strip()
        or os.getenv(_SHA_ENV, "").strip()
    )
    try:
        catalog, adapter_diagnostics = (
            _load_verified_cve_advisory_catalog_with_diagnostics()
        )
    except CveAdvisoryCatalogLoadError as exc:
        return None, {
            "configured": configured,
            "available": False,
            "verified": False,
            "source_name": None,
            "source_format": os.getenv(
                _FORMAT_ENV,
                "internal-v1",
            ).strip().lower(),
            "entry_count": 0,
            "adapter": None,
            "error": str(exc),
        }

    if catalog is None:
        return None, {
            "configured": False,
            "available": False,
            "verified": False,
            "source_name": None,
            "source_format": os.getenv(
                _FORMAT_ENV,
                "internal-v1",
            ).strip().lower(),
            "entry_count": 0,
            "adapter": None,
            "error": None,
        }
    return catalog, {
        "configured": True,
        "available": True,
        "verified": True,
        "source_name": catalog.source_name,
        "source_format": os.getenv(
            _FORMAT_ENV,
            "internal-v1",
        ).strip().lower(),
        "entry_count": catalog.entry_count,
        "adapter": adapter_diagnostics,
        "error": None,
    }


def cve_advisory_catalog_runtime_status() -> dict[str, Any]:
    _catalog, status = load_cve_advisory_catalog_with_status()
    return status
