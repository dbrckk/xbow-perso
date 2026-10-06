from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


VERSION_AMBIGUITY_SCHEMA = "version-ambiguity-v1"


@dataclass(frozen=True)
class VersionAmbiguity:
    schema: str
    ambiguous: bool
    reasons: tuple[str, ...]
    versioned_fingerprint_count: int
    high_confidence_versioned_count: int
    conflicting_product_count: int
    wildcard_cpe_count: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def _fingerprint_field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _cpe_version(value: str) -> str | None:
    parts = str(value).split(":")
    if len(parts) < 6 or parts[:2] != ["cpe", "2.3"]:
        return None
    return parts[5]


def analyze_version_ambiguity(
    finding: Any,
    fingerprints: Iterable[Any],
    *,
    high_confidence_threshold: float = 0.75,
) -> VersionAmbiguity:
    if not 0.5 <= float(high_confidence_threshold) <= 1.0:
        raise ValueError("high_confidence_threshold must be between 0.5 and 1.0")

    versioned: list[tuple[str, str, float]] = []
    versions_by_product: dict[str, set[str]] = {}
    for item in fingerprints:
        product = str(
            _fingerprint_field(item, "normalized_product", "") or ""
        ).strip()
        version = str(_fingerprint_field(item, "version", "") or "").strip()
        if not product or not version:
            continue
        try:
            confidence = float(_fingerprint_field(item, "confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        versioned.append((product, version, confidence))
        versions_by_product.setdefault(product, set()).add(version)

    conflicting_products = sum(
        len(versions) > 1
        for versions in versions_by_product.values()
    )
    high_confidence_count = sum(
        confidence >= high_confidence_threshold
        for _product, _version, confidence in versioned
    )

    cpe_values = getattr(finding, "cpe", None)
    if not isinstance(cpe_values, (list, tuple, set)):
        cpe_values = ()
    wildcard_cpe_count = 0
    for raw in cpe_values:
        version = _cpe_version(str(raw))
        if version in {"*", "-"}:
            wildcard_cpe_count += 1

    reasons: list[str] = []
    if conflicting_products:
        reasons.append("conflicting_version_fingerprints")
    if versioned and high_confidence_count == 0:
        reasons.append("low_confidence_version_fingerprints")
    if wildcard_cpe_count:
        reasons.append("wildcard_cpe_version")
    if not versioned and cpe_values:
        reasons.append("no_versioned_fingerprint")

    return VersionAmbiguity(
        schema=VERSION_AMBIGUITY_SCHEMA,
        ambiguous=bool(reasons),
        reasons=tuple(reasons),
        versioned_fingerprint_count=len(versioned),
        high_confidence_versioned_count=high_confidence_count,
        conflicting_product_count=conflicting_products,
        wildcard_cpe_count=wildcard_cpe_count,
    )
