from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


KEV_CATALOG_SCHEMA = "kev-catalog-v1"
_MAX_ENTRIES = 10000
_CVE_RE = re.compile(r"^CVE-(\d{4})-(\d{4,10})$", re.IGNORECASE)


class KevCatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class KevEntry:
    cve_id: str
    vendor_project: str
    product: str
    date_added: str
    due_date: str
    known_ransomware_campaign_use: str
    authoritative: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KevCatalog:
    schema: str
    source_name: str
    source_verified: bool
    catalog_version: str
    date_released: str
    source_digest_sha256: str
    entries: tuple[KevEntry, ...]
    entry_count: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entries"] = [entry.to_dict() for entry in self.entries]
        return payload


def _text(value: object, *, name: str, max_len: int = 512) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise KevCatalogError(f"{name} must be text")
    result = value.strip()
    if len(result) > max_len or any(
        ord(char) < 0x20 and char not in "\t" for char in result
    ):
        raise KevCatalogError(f"{name} is invalid")
    return result


def _normalize_cve(value: object) -> str:
    text = _text(value, name="cveID", max_len=32).upper()
    match = _CVE_RE.fullmatch(text)
    if not match:
        raise KevCatalogError("KEV entry CVE id is invalid")
    return f"CVE-{match.group(1)}-{match.group(2)}"


def _canonical_digest(document: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise KevCatalogError("KEV document is not JSON-serializable") from exc
    return hashlib.sha256(encoded).hexdigest()


def build_kev_catalog(
    document: Mapping[str, Any],
    *,
    source_name: str = "cisa-kev",
    source_verified: bool = False,
) -> KevCatalog:
    if not isinstance(document, Mapping):
        raise KevCatalogError("KEV document must be a mapping")
    if source_name != "cisa-kev":
        raise KevCatalogError("unsupported KEV source")

    raw_entries = document.get("vulnerabilities")
    if not isinstance(raw_entries, list):
        raise KevCatalogError("KEV vulnerabilities must be a list")
    if len(raw_entries) > _MAX_ENTRIES:
        raise KevCatalogError("KEV catalog exceeds entry limit")

    declared_count = document.get("count")
    if declared_count is not None:
        if (
            not isinstance(declared_count, int)
            or isinstance(declared_count, bool)
            or declared_count != len(raw_entries)
        ):
            raise KevCatalogError("KEV declared count does not match entries")

    catalog_version = _text(
        document.get("catalogVersion"),
        name="catalogVersion",
        max_len=80,
    )
    date_released = _text(
        document.get("dateReleased"),
        name="dateReleased",
        max_len=80,
    )

    by_cve: dict[str, KevEntry] = {}
    for raw in raw_entries:
        if not isinstance(raw, Mapping):
            raise KevCatalogError("KEV entry must be a mapping")
        cve_id = _normalize_cve(raw.get("cveID"))
        entry = KevEntry(
            cve_id=cve_id,
            vendor_project=_text(
                raw.get("vendorProject"),
                name="vendorProject",
                max_len=200,
            ),
            product=_text(raw.get("product"), name="product", max_len=200),
            date_added=_text(
                raw.get("dateAdded"),
                name="dateAdded",
                max_len=32,
            ),
            due_date=_text(
                raw.get("dueDate"),
                name="dueDate",
                max_len=32,
            ),
            known_ransomware_campaign_use=_text(
                raw.get("knownRansomwareCampaignUse"),
                name="knownRansomwareCampaignUse",
                max_len=80,
            ),
            authoritative=bool(source_verified),
        )
        existing = by_cve.get(cve_id)
        if existing is not None and existing != entry:
            raise KevCatalogError("conflicting duplicate KEV entry")
        by_cve[cve_id] = entry

    entries = tuple(by_cve[cve_id] for cve_id in sorted(by_cve))
    return KevCatalog(
        schema=KEV_CATALOG_SCHEMA,
        source_name=source_name,
        source_verified=bool(source_verified),
        catalog_version=catalog_version,
        date_released=date_released,
        source_digest_sha256=_canonical_digest(document),
        entries=entries,
        entry_count=len(entries),
    )


def authoritative_kev_ids(catalog: KevCatalog) -> frozenset[str]:
    if (
        catalog.schema != KEV_CATALOG_SCHEMA
        or catalog.source_name != "cisa-kev"
        or not catalog.source_verified
    ):
        return frozenset()
    return frozenset(
        entry.cve_id
        for entry in catalog.entries
        if entry.authoritative
    )


def finding_has_authoritative_kev(
    catalog: KevCatalog,
    cve_ids: list[str] | tuple[str, ...] | set[str],
) -> bool:
    authoritative = authoritative_kev_ids(catalog)
    return any(str(cve_id).upper() in authoritative for cve_id in cve_ids)
