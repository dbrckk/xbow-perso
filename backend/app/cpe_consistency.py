from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


CPE_CONSISTENCY_SCHEMA = "cpe-consistency-v1"


@dataclass(frozen=True)
class CpeConsistency:
    schema: str
    finding_id: str
    cpe_count: int
    parsed_cpe_count: int
    product_match_count: int
    generic_product_count: int
    mismatch_count: int
    vendor_match_count: int
    generic_vendor_count: int
    vendor_mismatch_count: int
    version_match_count: int
    generic_version_count: int
    version_mismatch_count: int
    reasons: tuple[str, ...]
    cpe_supports_product_identity: bool
    cpe_supports_vendor_identity: bool
    cpe_supports_version_identity: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def _normalize_token(value: object) -> str:
    return str(value or "").strip().lower().replace("_", " ").replace("-", " ")


def _parse_cpe23(value: object) -> tuple[str, str, str] | None:
    raw = str(value or "").strip()
    if not raw.startswith("cpe:2.3:"):
        return None
    parts = raw.split(":")
    if len(parts) != 13:
        return None
    vendor = parts[3].strip()
    product = parts[4].strip()
    version = parts[5].strip()
    return vendor, product, version


def build_cpe_consistency(
    finding: Any,
    *,
    observed_versions: Iterable[str] = (),
) -> CpeConsistency:
    raw_cpes = getattr(finding, "cpe", None)
    if isinstance(raw_cpes, str):
        cpes: tuple[object, ...] = (raw_cpes,)
    elif isinstance(raw_cpes, Iterable):
        cpes = tuple(raw_cpes)
    else:
        cpes = ()

    declared_product = _normalize_token(getattr(finding, "product", ""))
    declared_vendor = _normalize_token(getattr(finding, "vendor", ""))
    parsed = [item for item in (_parse_cpe23(value) for value in cpes) if item]

    normalized_observed_versions = {
        str(version).strip().lower()
        for version in observed_versions
        if str(version).strip()
    }

    matches = 0
    generic = 0
    mismatches = 0
    vendor_matches = 0
    generic_vendors = 0
    vendor_mismatches = 0
    version_matches = 0
    generic_versions = 0
    version_mismatches = 0
    for vendor, product, version in parsed:
        normalized_vendor = _normalize_token(vendor)
        if normalized_vendor in {"", "*", "-"}:
            generic_vendors += 1
        elif declared_vendor and normalized_vendor == declared_vendor:
            vendor_matches += 1
        elif declared_vendor:
            vendor_mismatches += 1

        normalized_product = _normalize_token(product)
        if normalized_product in {"", "*", "-"}:
            generic += 1
        elif declared_product and normalized_product == declared_product:
            matches += 1
        elif declared_product:
            mismatches += 1

        normalized_version = str(version or "").strip().lower()
        if normalized_version in {"", "*", "-"}:
            generic_versions += 1
        elif normalized_observed_versions:
            if normalized_version in normalized_observed_versions:
                version_matches += 1
            else:
                version_mismatches += 1

    reasons: set[str] = set()
    if cpes and len(parsed) != len(cpes):
        reasons.add("unparseable_cpe")
    if generic:
        reasons.add("generic_cpe_product")
    if mismatches:
        reasons.add("cpe_product_mismatch")
    if cpes and not declared_product:
        reasons.add("declared_product_missing")
    if generic_vendors and declared_vendor:
        reasons.add("generic_cpe_vendor")
    if vendor_mismatches:
        reasons.add("cpe_vendor_mismatch")
    if cpes and not declared_vendor:
        reasons.add("declared_vendor_missing")
    if generic_versions and normalized_observed_versions:
        reasons.add("generic_cpe_version")
    if version_mismatches:
        reasons.add("cpe_version_mismatch")

    supports = bool(
        declared_product
        and matches > 0
        and mismatches == 0
        and generic == 0
        and len(parsed) == len(cpes)
    )

    supports_vendor = bool(
        declared_vendor
        and vendor_matches > 0
        and vendor_mismatches == 0
        and generic_vendors == 0
        and len(parsed) == len(cpes)
    )

    supports_version = bool(
        supports
        and normalized_observed_versions
        and version_matches > 0
        and version_mismatches == 0
        and generic_versions == 0
    )

    return CpeConsistency(
        schema=CPE_CONSISTENCY_SCHEMA,
        finding_id=str(getattr(finding, "id", "")),
        cpe_count=len(cpes),
        parsed_cpe_count=len(parsed),
        product_match_count=matches,
        generic_product_count=generic,
        mismatch_count=mismatches,
        vendor_match_count=vendor_matches,
        generic_vendor_count=generic_vendors,
        vendor_mismatch_count=vendor_mismatches,
        version_match_count=version_matches,
        generic_version_count=generic_versions,
        version_mismatch_count=version_mismatches,
        reasons=tuple(sorted(reasons)),
        cpe_supports_product_identity=supports,
        cpe_supports_vendor_identity=supports_vendor,
        cpe_supports_version_identity=supports_version,
    )
