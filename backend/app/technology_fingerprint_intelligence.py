from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .observation_graph import ObservationGraph


_VERSIONED_TECH_RE = re.compile(
    r"^\s*(?P<product>[A-Za-z][A-Za-z0-9 ._+\-]{0,80}?)"
    r"(?:[/\s:vV_-]+)(?P<version>[0-9]+(?:\.[0-9A-Za-z_-]+){0,5})\s*$"
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+\-]{1,80}")


@dataclass(frozen=True)
class TechnologyFingerprint:
    product: str
    normalized_product: str
    version: str | None
    confidence: float
    sources: tuple[str, ...]
    observation_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sources"] = list(self.sources)
        payload["observation_ids"] = list(self.observation_ids)
        return payload


def _normalize_product(value: str) -> str:
    tokens = _TOKEN_RE.findall(value.lower())
    return " ".join(tokens[:8]).strip()


def _parse_technology(value: str) -> tuple[str, str | None]:
    raw = str(value or "").strip()
    match = _VERSIONED_TECH_RE.fullmatch(raw)
    if match:
        product = match.group("product").strip(" -_./:")
        version = match.group("version")
        return product, version
    return raw[:120], None


def build_technology_fingerprints(
    graph: ObservationGraph,
) -> tuple[TechnologyFingerprint, ...]:
    grouped: dict[tuple[str, str | None], dict[str, Any]] = {}

    for observation in graph.by_kind("technology"):
        product, version = _parse_technology(observation.value)
        normalized = _normalize_product(product)
        if not normalized:
            continue
        key = (normalized, version)
        current = grouped.setdefault(
            key,
            {
                "product": product,
                "sources": set(),
                "observation_ids": set(),
                "explicit_confidences": [],
            },
        )
        current["sources"].add(str(observation.source))
        current["observation_ids"].add(str(observation.id))
        raw_confidence = observation.metadata.get("confidence")
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None and 0.0 <= confidence <= 1.0:
            current["explicit_confidences"].append(confidence)

    result: list[TechnologyFingerprint] = []
    for (normalized, version), payload in grouped.items():
        sources = tuple(sorted(payload["sources"]))
        explicit = payload["explicit_confidences"]
        base = 0.45
        if version:
            base += 0.20
        base += min(0.25, max(0, len(sources) - 1) * 0.125)
        if explicit:
            base = max(base, sum(explicit) / len(explicit))
        confidence = round(min(1.0, base), 3)

        result.append(
            TechnologyFingerprint(
                product=str(payload["product"]),
                normalized_product=normalized,
                version=version,
                confidence=confidence,
                sources=sources,
                observation_ids=tuple(sorted(payload["observation_ids"])),
            )
        )

    result.sort(
        key=lambda item: (
            -item.confidence,
            item.normalized_product,
            item.version or "",
        )
    )
    return tuple(result)


def match_finding_technology(
    finding: Any,
    fingerprints: tuple[TechnologyFingerprint, ...],
) -> tuple[TechnologyFingerprint, ...]:
    parts = []
    for name in ("title", "summary", "impact", "remediation"):
        value = getattr(finding, name, None)
        if value:
            parts.append(str(value))
    evidence = getattr(finding, "evidence", None)
    if isinstance(evidence, (list, tuple)):
        parts.extend(str(item) for item in evidence if item)
    haystack = _normalize_product(" ".join(parts))

    matches = []
    for fingerprint in fingerprints:
        product = fingerprint.normalized_product
        if product and product in haystack:
            matches.append(fingerprint)
    return tuple(matches)


def build_finding_fingerprint_intelligence(
    findings: list[Any],
    graph: ObservationGraph,
) -> dict[str, Any]:
    fingerprints = build_technology_fingerprints(graph)
    rows = []
    for finding in sorted(findings, key=lambda item: str(getattr(item, "id", ""))):
        matched = match_finding_technology(finding, fingerprints)
        rows.append(
            {
                "finding_id": str(getattr(finding, "id", "")),
                "matched_fingerprints": [item.to_dict() for item in matched],
                "versioned_match_count": sum(item.version is not None for item in matched),
                "high_confidence_match_count": sum(
                    item.confidence >= 0.75 for item in matched
                ),
            }
        )

    return {
        "fingerprints": [item.to_dict() for item in fingerprints],
        "findings": rows,
        "summary": {
            "technology_fingerprints": len(fingerprints),
            "versioned_fingerprints": sum(
                item.version is not None for item in fingerprints
            ),
            "multi_source_fingerprints": sum(
                len(item.sources) >= 2 for item in fingerprints
            ),
            "findings_with_versioned_match": sum(
                row["versioned_match_count"] > 0 for row in rows
            ),
        },
        "read_only": True,
        "advisory_only": True,
        "automatic_exploitation": False,
    }
