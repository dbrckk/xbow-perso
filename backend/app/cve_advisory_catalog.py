from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
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
    identity_kind: str
    vendor: str | None
    product: str | None
    package_ecosystem: str | None
    package_name: str | None
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
    source_authority: str
    source_verified: bool
    source_snapshot_at: str | None
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


def _optional_snapshot_at(value: object) -> str | None:
    if value is None or value == "":
        return None
    raw = _text(
        value,
        name="source_snapshot_at",
        max_len=80,
    )
    try:
        parsed = datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise CveAdvisoryCatalogError(
            "source_snapshot_at is invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise CveAdvisoryCatalogError(
            "source_snapshot_at must include a timezone"
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _optional_identity(value: object, *, name: str) -> str | None:
    if value is None or value == "":
        return None
    return _normalize_identity(value, name=name)


def _optional_package_ecosystem(value: object) -> str | None:
    if value is None or value == "":
        return None
    return _text(
        value,
        name="package_ecosystem",
        max_len=120,
    ).lower()


def _optional_package_name(value: object) -> str | None:
    if value is None or value == "":
        return None
    return _text(
        value,
        name="package_name",
        max_len=240,
    )


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
    source_authority: str | None = None,
    source_verified: bool = False,
    source_snapshot_at: str | None = None,
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
    normalized_authority = _text(
        source_authority or normalized_source,
        name="source_authority",
        max_len=120,
    ).lower()
    normalized_snapshot_at = _optional_snapshot_at(
        source_snapshot_at
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

    by_key: dict[
        tuple[str, str, str, str],
        CveAdvisoryEntry,
    ] = {}
    for raw in raw_entries:
        if not isinstance(raw, Mapping):
            raise CveAdvisoryCatalogError(
                "advisory entry must be a mapping"
            )
        cve_id = _normalize_cve(raw.get("cve_id"))
        vendor = _optional_identity(raw.get("vendor"), name="vendor")
        product = _optional_identity(raw.get("product"), name="product")
        package_ecosystem = _optional_package_ecosystem(
            raw.get("package_ecosystem")
        )
        package_name = _optional_package_name(
            raw.get("package_name")
        )

        if (vendor is None) != (product is None):
            raise CveAdvisoryCatalogError(
                "vendor/product advisory identity is incomplete"
            )
        if (package_ecosystem is None) != (package_name is None):
            raise CveAdvisoryCatalogError(
                "package advisory identity is incomplete"
            )

        cpe_identity = vendor is not None and product is not None
        package_identity = (
            package_ecosystem is not None
            and package_name is not None
        )
        if cpe_identity == package_identity:
            raise CveAdvisoryCatalogError(
                "advisory entry must define exactly one identity kind"
            )
        identity_kind = "cpe" if cpe_identity else "package"

        entry = CveAdvisoryEntry(
            cve_id=cve_id,
            identity_kind=identity_kind,
            vendor=vendor,
            product=product,
            package_ecosystem=package_ecosystem,
            package_name=package_name,
            affected_version_ranges=_ranges(
                raw.get("affected_version_ranges")
            ),
            authoritative=bool(source_verified),
        )
        key = (
            cve_id,
            identity_kind,
            vendor if cpe_identity else package_ecosystem or "",
            product if cpe_identity else package_name or "",
        )
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
        source_authority=normalized_authority,
        source_verified=bool(source_verified),
        source_snapshot_at=normalized_snapshot_at,
        source_digest_sha256=_canonical_digest(document),
        entries=entries,
        entry_count=len(entries),
    )


def find_verified_cve_advisories(
    catalog: CveAdvisoryCatalog,
    *,
    cve_id: str,
    vendor: str | None = None,
    product: str | None = None,
    package_ecosystem: str | None = None,
    package_name: str | None = None,
) -> tuple[CveAdvisoryEntry, ...]:
    if (
        catalog.schema != CVE_ADVISORY_CATALOG_SCHEMA
        or not catalog.source_verified
    ):
        return ()

    try:
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
        normalized_package_ecosystem = (
            _optional_package_ecosystem(package_ecosystem)
            if package_ecosystem
            else None
        )
        normalized_package_name = (
            _optional_package_name(package_name)
            if package_name
            else None
        )
    except CveAdvisoryCatalogError:
        return ()

    if (normalized_vendor is None) != (normalized_product is None):
        return ()
    if (
        (normalized_package_ecosystem is None)
        != (normalized_package_name is None)
    ):
        return ()

    matches: list[CveAdvisoryEntry] = []
    for entry in catalog.entries:
        if not entry.authoritative or entry.cve_id != normalized_cve:
            continue
        if (
            entry.identity_kind == "cpe"
            and normalized_vendor is not None
            and normalized_product is not None
            and entry.vendor == normalized_vendor
            and entry.product == normalized_product
        ):
            matches.append(entry)
        elif (
            entry.identity_kind == "package"
            and normalized_package_ecosystem is not None
            and normalized_package_name is not None
            and entry.package_ecosystem == normalized_package_ecosystem
            and entry.package_name == normalized_package_name
        ):
            matches.append(entry)

    return tuple(
        sorted(
            matches,
            key=lambda item: (
                item.identity_kind,
                item.vendor or item.package_ecosystem or "",
                item.product or item.package_name or "",
            ),
        )
    )


def find_verified_cve_advisory(
    catalog: CveAdvisoryCatalog,
    *,
    cve_id: str,
    vendor: str | None = None,
    product: str | None = None,
    package_ecosystem: str | None = None,
    package_name: str | None = None,
) -> CveAdvisoryEntry | None:
    matches = find_verified_cve_advisories(
        catalog,
        cve_id=cve_id,
        vendor=vendor,
        product=product,
        package_ecosystem=package_ecosystem,
        package_name=package_name,
    )
    if len(matches) != 1:
        return None
    return matches[0]
