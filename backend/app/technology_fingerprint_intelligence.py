from __future__ import annotations

import re
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

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
    asset_observation_ids: tuple[str, ...] = ()
    asset_values: tuple[str, ...] = ()
    latest_observed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sources"] = list(self.sources)
        payload["observation_ids"] = list(self.observation_ids)
        payload["asset_observation_ids"] = list(
            self.asset_observation_ids
        )
        payload["asset_values"] = list(self.asset_values)
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


def _asset_key(value: object) -> str:
    identity = _asset_identity(value)
    if identity is None:
        return ""
    host, scheme, port = identity
    if scheme in {"http", "https"} and port is not None:
        return f"{scheme}://{host}:{port}"
    if port is not None:
        return f"{host}:{port}"
    return host


def _asset_identity(value: object) -> tuple[str, str | None, int | None] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw if "://" in raw else f"//{raw}")
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or parsed.username is not None or parsed.password is not None:
            return None
        scheme = parsed.scheme.lower() or None
        if scheme not in {None, "http", "https"}:
            return None
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
    return host, scheme, port


def _compatible_asset_identity(direct_value: object, graph_value: object) -> bool:
    """Compare known origin components without guessing unspecified ones."""
    direct = _asset_identity(direct_value)
    linked = _asset_identity(graph_value)
    if direct is None or linked is None:
        return False
    direct_host, direct_scheme, direct_port = direct
    linked_host, linked_scheme, linked_port = linked
    if direct_host != linked_host:
        return False
    if direct_scheme and linked_scheme and direct_scheme != linked_scheme:
        return False
    if direct_port is not None and linked_port is not None:
        if direct_port != linked_port:
            return False
    return True


def _asset_ancestor_ids(
    graph: ObservationGraph,
    observation_id: str,
) -> tuple[str, ...]:
    items = {item.id: item for item in graph.values()}
    pending = (
        list(items[observation_id].parent_ids)
        if observation_id in items
        else []
    )
    seen: set[str] = set()
    assets: set[str] = set()
    while pending:
        parent_id = pending.pop()
        if parent_id in seen:
            continue
        seen.add(parent_id)
        parent = items.get(parent_id)
        if parent is None:
            continue
        if parent.kind == "asset":
            assets.add(parent.id)
            continue
        pending.extend(parent.parent_ids)
    return tuple(sorted(assets))


def _asset_scope(
    graph: ObservationGraph,
    observation_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    items = {item.id: item for item in graph.values()}
    asset_ids = _asset_ancestor_ids(graph, observation_id)
    asset_values = tuple(
        sorted(
            {
                str(items[asset_id].value)
                for asset_id in asset_ids
                if asset_id in items
            }
        )
    )
    asset_keys = tuple(
        sorted(
            {
                key
                for value in asset_values
                if (key := _asset_key(value))
            }
        )
    )
    return asset_ids, asset_values, asset_keys


def _finding_asset_keys(
    finding: Any,
    graph: ObservationGraph | None,
) -> tuple[str, ...]:
    keys: set[str] = set()
    direct_value = str(getattr(finding, "asset", "") or "").strip()
    direct = _asset_key(direct_value)
    if direct_value and not direct:
        return ()
    if direct:
        keys.add(direct)
    if graph is None:
        return tuple(sorted(keys))

    finding_id = str(getattr(finding, "id", "") or "")
    linked_asset_values: set[str] = set()
    for observation in graph.by_kind("finding"):
        if (
            observation.id == f"finding:{finding_id}"
            or observation.id == finding_id
            or str(observation.value) == finding_id
        ):
            _asset_ids, asset_values, _asset_keys = _asset_scope(
                graph,
                observation.id,
            )
            linked_asset_values.update(asset_values)
            if direct_value and any(
                not _compatible_asset_identity(direct_value, value)
                for value in asset_values
            ):
                # Declared asset and graph lineage disagree: do not merge
                # their keys into a false corroboration.
                return ()
            keys.update(
                key
                for value in asset_values
                if (key := _asset_key(value))
            )
    if any(
        not _compatible_asset_identity(left, right)
        for left in linked_asset_values
        for right in linked_asset_values
    ):
        # A hostname-only declared asset must not hide contradictory
        # origin-specific graph parents (such as HTTP and HTTPS).
        return ()
    return tuple(sorted(keys))


def filter_fingerprints_for_finding_asset(
    finding: Any,
    fingerprints: tuple[TechnologyFingerprint, ...],
    graph: ObservationGraph | None = None,
) -> tuple[TechnologyFingerprint, ...]:
    raw_asset = str(getattr(finding, "asset", "") or "").strip()
    if raw_asset and not _asset_key(raw_asset):
        # Never fall back to legacy unscoped evidence for malformed assets.
        return ()
    finding_keys = set(_finding_asset_keys(finding, graph))
    scoped_present = any(item.asset_values for item in fingerprints)
    graph_asset_keys: set[str] = set()

    if graph is not None:
        graph_asset_keys = {
            key
            for observation in graph.by_kind("asset")
            if (key := _asset_key(observation.value))
        }
        if not finding_keys and graph_asset_keys:
            return ()
        if (
            finding_keys
            and graph_asset_keys
            and not (finding_keys & graph_asset_keys)
        ):
            return ()

    if finding_keys and scoped_present:
        matches = []
        for fingerprint in fingerprints:
            fingerprint_keys = {
                key
                for value in fingerprint.asset_values
                if (key := _asset_key(value))
            }
            if fingerprint_keys and fingerprint_keys <= finding_keys:
                # One observation linked to multiple distinct origins
                # cannot count as evidence for just one of those origins.
                matches.append(fingerprint)
        return tuple(matches)

    if graph_asset_keys:
        # A graph asset without a linked technology observation is not
        # evidence that an unscoped fingerprint belongs to that asset.
        return ()

    return fingerprints


def build_technology_fingerprints(
    graph: ObservationGraph,
) -> tuple[TechnologyFingerprint, ...]:
    grouped: dict[
        tuple[tuple[str, ...], str, str | None],
        dict[str, Any],
    ] = {}

    for observation in graph.by_kind("technology"):
        product, version = _parse_technology(observation.value)
        normalized = _normalize_product(product)
        if not normalized:
            continue
        asset_ids, asset_values, asset_keys = _asset_scope(
            graph,
            observation.id,
        )
        key = (asset_keys, normalized, version)
        current = grouped.setdefault(
            key,
            {
                "product": product,
                "sources": set(),
                "observation_ids": set(),
                "asset_observation_ids": set(),
                "asset_values": set(),
                "explicit_confidences": [],
                "observed_at": [],
            },
        )
        current["sources"].add(str(observation.source))
        current["observation_ids"].add(str(observation.id))
        current["asset_observation_ids"].update(asset_ids)
        current["asset_values"].update(asset_values)
        for timestamp_key in ("observed_at", "collected_at", "timestamp"):
            raw_timestamp = observation.metadata.get(timestamp_key)
            if not raw_timestamp:
                continue
            try:
                parsed_timestamp = datetime.fromisoformat(
                    str(raw_timestamp).replace("Z", "+00:00")
                )
            except ValueError:
                break
            if parsed_timestamp.tzinfo is None:
                parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
            current["observed_at"].append(
                parsed_timestamp.astimezone(timezone.utc)
            )
            break

        raw_confidence = observation.metadata.get("confidence")
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None and 0.0 <= confidence <= 1.0:
            current["explicit_confidences"].append(confidence)

    result: list[TechnologyFingerprint] = []
    for (_asset_keys, normalized, version), payload in grouped.items():
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
                asset_observation_ids=tuple(
                    sorted(payload["asset_observation_ids"])
                ),
                asset_values=tuple(sorted(payload["asset_values"])),
                latest_observed_at=(
                    max(payload["observed_at"]).isoformat()
                    if payload["observed_at"]
                    else None
                ),
            )
        )

    result.sort(
        key=lambda item: (
            -item.confidence,
            tuple(_asset_key(value) for value in item.asset_values),
            item.normalized_product,
            item.version or "",
        )
    )
    return tuple(result)


def match_finding_technology(
    finding: Any,
    fingerprints: tuple[TechnologyFingerprint, ...],
    graph: ObservationGraph | None = None,
) -> tuple[TechnologyFingerprint, ...]:
    parts = []
    for name in ("title", "summary", "impact", "remediation", "product"):
        value = getattr(finding, name, None)
        if value:
            parts.append(str(value))
    evidence = getattr(finding, "evidence", None)
    if isinstance(evidence, (list, tuple)):
        parts.extend(str(item) for item in evidence if item)
    haystack = _normalize_product(" ".join(parts))

    matches = []
    scoped_fingerprints = filter_fingerprints_for_finding_asset(
        finding,
        fingerprints,
        graph,
    )
    for fingerprint in scoped_fingerprints:
        product = fingerprint.normalized_product
        if product and product in haystack:
            matches.append(fingerprint)
    return tuple(matches)




def finding_product_ambiguity_reasons(
    finding: Any,
    fingerprints: tuple[TechnologyFingerprint, ...],
    graph: ObservationGraph | None = None,
) -> tuple[str, ...]:
    declared = _normalize_product(str(getattr(finding, "product", "") or ""))
    if not declared or not fingerprints:
        return ()

    scoped_fingerprints = filter_fingerprints_for_finding_asset(
        finding,
        fingerprints,
        graph,
    )
    observed = {
        item.normalized_product
        for item in scoped_fingerprints
        if item.normalized_product
    }
    if declared in observed:
        return ()

    return ("declared_product_not_observed",)

def fingerprint_ambiguity_reasons(
    fingerprints: tuple[TechnologyFingerprint, ...],
) -> tuple[str, ...]:
    """Return conservative ambiguity markers for conflicting matched versions."""
    versions_by_product: dict[str, set[str]] = {}
    for item in fingerprints:
        if not item.version:
            continue
        versions_by_product.setdefault(item.normalized_product, set()).add(item.version)

    reasons: set[str] = set()
    if any(len(versions) > 1 for versions in versions_by_product.values()):
        reasons.add("conflicting_version_fingerprints")

    versioned = [item for item in fingerprints if item.version]
    if versioned and all(len(item.sources) < 2 for item in versioned):
        reasons.add("single_source_version_evidence")

    return tuple(sorted(reasons))


def fingerprint_staleness_reasons(
    fingerprints: tuple[TechnologyFingerprint, ...],
    *,
    now: datetime | None = None,
    max_age_days: int = 30,
) -> tuple[str, ...]:
    if max_age_days < 1:
        raise ValueError("max_age_days must be positive")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    versioned = [item for item in fingerprints if item.version]
    timestamped = [item for item in versioned if item.latest_observed_at]
    if not timestamped:
        return ()

    fresh = False
    for item in timestamped:
        try:
            observed = datetime.fromisoformat(
                str(item.latest_observed_at).replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        age_seconds = (current - observed.astimezone(timezone.utc)).total_seconds()
        if age_seconds < 0:
            continue
        if age_seconds <= max_age_days * 86400:
            fresh = True
            break

    if fresh:
        return ()

    if len(timestamped) == len(versioned):
        return ("stale_version_fingerprints",)
    return ("partially_stale_version_fingerprints",)

def build_finding_fingerprint_intelligence(
    findings: list[Any],
    graph: ObservationGraph,
) -> dict[str, Any]:
    fingerprints = build_technology_fingerprints(graph)
    rows = []
    for finding in sorted(findings, key=lambda item: str(getattr(item, "id", ""))):
        matched = match_finding_technology(
            finding,
            fingerprints,
            graph,
        )
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
