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


_MAX_CATALOG_BYTES = 8 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_ENV = "XBOW_CVE_ADVISORY_CATALOG_PATH"
_SHA_ENV = "XBOW_CVE_ADVISORY_CATALOG_SHA256"
_SOURCE_ENV = "XBOW_CVE_ADVISORY_CATALOG_SOURCE"


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


def load_verified_cve_advisory_catalog() -> CveAdvisoryCatalog | None:
    path_raw = os.getenv(_PATH_ENV, "").strip()
    digest_raw = os.getenv(_SHA_ENV, "").strip().lower()

    if not path_raw and not digest_raw:
        return None
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

    source_name = os.getenv(
        _SOURCE_ENV,
        "pinned-cve-advisory-file",
    ).strip()
    try:
        return build_cve_advisory_catalog(
            document,
            source_name=source_name,
            source_verified=True,
        )
    except CveAdvisoryCatalogError as exc:
        raise CveAdvisoryCatalogLoadError(
            "CVE advisory catalog schema validation failed"
        ) from exc


def load_cve_advisory_catalog_with_status(
) -> tuple[CveAdvisoryCatalog | None, dict[str, Any]]:
    configured = bool(
        os.getenv(_PATH_ENV, "").strip()
        or os.getenv(_SHA_ENV, "").strip()
    )
    try:
        catalog = load_verified_cve_advisory_catalog()
    except CveAdvisoryCatalogLoadError as exc:
        return None, {
            "configured": configured,
            "available": False,
            "verified": False,
            "source_name": None,
            "entry_count": 0,
            "error": str(exc),
        }

    if catalog is None:
        return None, {
            "configured": False,
            "available": False,
            "verified": False,
            "source_name": None,
            "entry_count": 0,
            "error": None,
        }
    return catalog, {
        "configured": True,
        "available": True,
        "verified": True,
        "source_name": catalog.source_name,
        "entry_count": catalog.entry_count,
        "error": None,
    }


def cve_advisory_catalog_runtime_status() -> dict[str, Any]:
    _catalog, status = load_cve_advisory_catalog_with_status()
    return status
