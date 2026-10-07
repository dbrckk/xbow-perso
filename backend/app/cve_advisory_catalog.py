from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


CVE_ADVISORY_CATALOG_SCHEMA = "cve-advisory-catalog-v1"
_MAX_ENTRIES = 20000
_MAX_RANGES = 16
_CVE_RE = re.compile(r"^CVE-(\d{4})-(\d{4,10})$", re.IGNORECASE)


class CveAdvisoryCatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class CveAdvisoryEntry:
    cve_id: str
    vendor: str
    product: str
    affected_version_ranges: tuple[str, ...]
    authoritative: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["affected_version_ranges"] = list(self.affected_version_ranges)
        return payload


@dataclass(frozen=True)
class CveAdvisoryCatalog:
    schema: str
    source_name: str
    source_verified: bool
    source_digest_sha256: str
    entries: tuple[CveAdvisoryEntry, ...]
    entry_count: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entries"] = [entry.to_dict() for entry in self.entries]
        return payload


def _text(
    value: object,
    *,
    name: str,
    max_len: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise CveAdvisoryCatalogError(f"{name} must be text")
    result = value.strip()
    if (
        (not result and not allow_empty)
        or len(result) > max_len
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in result)
    ):
        raise CveAdvisoryCatalogError(f"{name} is invalid")
    return result


def _normalize_cve(value: object) -> str:
    text = _text(value, name="cve_id", max_len=32).upper()
    match = _CVE_RE.fullmatch(text)
    if not match:
        raise CveAdvisoryCatalogError("advisory CVE id is invalid")
    return f"CVE-{match.group(1)}-{match.group(2)}"


def _normalize_identity(value: object, *, name: str) -> str:
    return _text(value, name=name, max_len=200).lower()


def _ranges(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise CveAdvisoryCatalogError(
            "affected_version_ranges must be a list"
        )
    if not 1 <= len(value) <= _MAX_RANGES:
        raise CveAdvisoryCatalogError(
            "affected_version_ranges count is invalid"
        )

    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        item = _text(
            raw,
            name="affected_version_range",
            max_len=128,
        )
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    if not result:
        raise CveAdvisoryCatalogError(
            "affected_version_ranges must not be empty"
        )
    return tuple(result)


def _canonical_digest(document: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CveAdvisoryCatalogError(
            "advisory document is not JSON-serializable"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def build_cve_advisory_catalog(
    document: Mapping[str, Any],
    *,
    source_name: str,
    source_verified: bool = False,
) -> CveAdvisoryCatalog:
    if not isinstance(document, Mapping):
        raise CveAdvisoryCatalogError(
            "advisory document must be a mapping"
        )
    normalized_source = _text(
        source_name,
        name="source_name",
        max_len=120,
    )
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise CveAdvisoryCatalogError("advisory entries must be a list")
    if len(raw_entries) > _MAX_ENTRIES:
        raise CveAdvisoryCatalogError("advisory catalog exceeds entry limit")

    declared_count = document.get("count")
    if declared_count is not None and (
        not isinstance(declared_count, int)
        or isinstance(declared_count, bool)
        or declared_count != len(raw_entries)
    ):
        raise CveAdvisoryCatalogError(
            "advisory declared count does not match entries"
        )

    by_key: dict[tuple[str, str, str], CveAdvisoryEntry] = {}
    for raw in raw_entries:
        if not isinstance(raw, Mapping):
            raise CveAdvisoryCatalogError(
                "advisory entry must be a mapping"
            )
        cve_id = _normalize_cve(raw.get("cve_id"))
        vendor = _normalize_identity(raw.get("vendor"), name="vendor")
        product = _normalize_identity(raw.get("product"), name="product")
        entry = CveAdvisoryEntry(
            cve_id=cve_id,
            vendor=vendor,
            product=product,
            affected_version_ranges=_ranges(
                raw.get("affected_version_ranges")
            ),
            authoritative=bool(source_verified),
        )
        key = (cve_id, vendor, product)
        existing = by_key.get(key)
        if existing is not None and existing != entry:
            raise CveAdvisoryCatalogError(
                "conflicting duplicate advisory entry"
            )
        by_key[key] = entry

    entries = tuple(
        by_key[key]
        for key in sorted(by_key)
    )
    return CveAdvisoryCatalog(
        schema=CVE_ADVISORY_CATALOG_SCHEMA,
        source_name=normalized_source,
        source_verified=bool(source_verified),
        source_digest_sha256=_canonical_digest(document),
        entries=entries,
        entry_count=len(entries),
    )


def find_verified_cve_advisory(
    catalog: CveAdvisoryCatalog,
    *,
    cve_id: str,
    vendor: str | None = None,
    product: str | None = None,
) -> CveAdvisoryEntry | None:
    if (
        catalog.schema != CVE_ADVISORY_CATALOG_SCHEMA
        or not catalog.source_verified
    ):
        return None

    normalized_cve = _normalize_cve(cve_id)
    normalized_vendor = (
        _normalize_identity(vendor, name="vendor")
        if vendor
        else None
    )
    normalized_product = (
        _normalize_identity(product, name="product")
        if product
        else None
    )

    matches = [
        entry
        for entry in catalog.entries
        if entry.authoritative
        and entry.cve_id == normalized_cve
        and (
            normalized_vendor is None
            or entry.vendor == normalized_vendor
        )
        and (
            normalized_product is None
            or entry.product == normalized_product
        )
    ]
    if len(matches) != 1:
        return None
    return matches[0]
