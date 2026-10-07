from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .vulnerability_intelligence import finding_cve_ids


AFFECTED_VERSION_RANGE_SCHEMA = "affected-version-range-v1"
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,5}$")
_CLAUSE_RE = re.compile(r"^(<=|>=|<|>|==|=)?\s*([0-9]+(?:\.[0-9]+){0,5})$")


@dataclass(frozen=True)
class AffectedVersionRangeEvidence:
    schema: str
    finding_id: str
    ranges: tuple[str, ...]
    observed_versions: tuple[str, ...]
    matching_versions: tuple[str, ...]
    outside_versions: tuple[str, ...]
    unparseable_ranges: tuple[str, ...]
    state: str
    range_binding: str
    binding_ambiguity_reason: str | None
    range_source: str | None
    range_source_verified: bool
    range_provenance_state: str
    affected_version_supported: bool
    trusted_affected_version_supported: bool
    exploitability_confirmed: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for name in (
            "ranges",
            "observed_versions",
            "matching_versions",
            "outside_versions",
            "unparseable_ranges",
        ):
            payload[name] = list(payload[name])
        return payload


def _version_tuple(value: str) -> tuple[int, ...] | None:
    normalized = str(value or "").strip()
    if not _VERSION_RE.fullmatch(normalized):
        return None
    parts = tuple(int(part) for part in normalized.split("."))
    return parts + (0,) * (6 - len(parts))


def _clause_matches(version: tuple[int, ...], clause: str) -> bool | None:
    match = _CLAUSE_RE.fullmatch(clause.strip())
    if not match:
        return None
    operator = match.group(1) or "="
    target = _version_tuple(match.group(2))
    if target is None:
        return None
    if operator in {"=", "=="}:
        return version == target
    if operator == "<":
        return version < target
    if operator == "<=":
        return version <= target
    if operator == ">":
        return version > target
    if operator == ">=":
        return version >= target
    return None


def _range_matches(version: tuple[int, ...], expression: str) -> bool | None:
    clauses = [part.strip() for part in expression.split(",")]
    if not clauses or len(clauses) > 4 or any(not part for part in clauses):
        return None
    outcomes = [_clause_matches(version, clause) for clause in clauses]
    if any(item is None for item in outcomes):
        return None
    return all(bool(item) for item in outcomes)


def build_affected_version_range_evidence(
    finding: Any,
    *,
    observed_versions: Iterable[str] = (),
) -> AffectedVersionRangeEvidence:
    raw_ranges = getattr(finding, "affected_version_ranges", None) or ()
    if isinstance(raw_ranges, str):
        raw_ranges = (raw_ranges,)
    ranges = tuple(
        str(item).strip()
        for item in tuple(raw_ranges)[:16]
        if str(item).strip()
    )
    observed = tuple(
        sorted(
            {
                str(item).strip()
                for item in observed_versions
                if str(item).strip()
            }
        )
    )
    cve_ids = finding_cve_ids(finding)
    raw_source = str(
        getattr(finding, "affected_version_range_source", "") or ""
    ).strip()
    range_source = raw_source[:120] or None
    range_source_verified = bool(
        range_source
        and getattr(finding, "affected_version_range_verified", None) is True
    )
    if range_source_verified:
        range_provenance_state = "verified"
    elif range_source:
        range_provenance_state = "unverified"
    else:
        range_provenance_state = "missing"

    if not ranges:
        state = "not_available"
        return AffectedVersionRangeEvidence(
            schema=AFFECTED_VERSION_RANGE_SCHEMA,
            finding_id=str(getattr(finding, "id", "")),
            ranges=(),
            observed_versions=observed,
            matching_versions=(),
            outside_versions=(),
            unparseable_ranges=(),
            state=state,
            range_binding="no_ranges",
            binding_ambiguity_reason=None,
            range_source=range_source,
            range_source_verified=range_source_verified,
            range_provenance_state=range_provenance_state,
            affected_version_supported=False,
            trusted_affected_version_supported=False,
            exploitability_confirmed=False,
        )

    if len(cve_ids) != 1:
        reason = (
            "multiple_cves_share_unbound_ranges"
            if len(cve_ids) > 1
            else "affected_range_without_cve"
        )
        return AffectedVersionRangeEvidence(
            schema=AFFECTED_VERSION_RANGE_SCHEMA,
            finding_id=str(getattr(finding, "id", "")),
            ranges=ranges,
            observed_versions=observed,
            matching_versions=(),
            outside_versions=(),
            unparseable_ranges=(),
            state="unknown",
            range_binding=(
                "ambiguous_multi_cve"
                if len(cve_ids) > 1
                else "no_cve_binding"
            ),
            binding_ambiguity_reason=reason,
            range_source=range_source,
            range_source_verified=range_source_verified,
            range_provenance_state=range_provenance_state,
            affected_version_supported=False,
            trusted_affected_version_supported=False,
            exploitability_confirmed=False,
        )

    parseable_ranges: list[str] = []
    unparseable: list[str] = []
    for expression in ranges:
        probe = _range_matches((0, 0, 0, 0, 0, 0), expression)
        if probe is None:
            unparseable.append(expression)
        else:
            parseable_ranges.append(expression)

    matching: list[str] = []
    outside: list[str] = []
    unparseable_observed = False
    for raw_version in observed:
        version = _version_tuple(raw_version)
        if version is None:
            unparseable_observed = True
            continue
        if any(
            _range_matches(version, expression) is True
            for expression in parseable_ranges
        ):
            matching.append(raw_version)
        elif parseable_ranges:
            outside.append(raw_version)

    if not observed or unparseable_observed or not parseable_ranges:
        state = "unknown"
    elif matching and outside:
        state = "mixed"
    elif matching:
        state = "affected"
    elif outside:
        state = "not_affected"
    else:
        state = "unknown"

    return AffectedVersionRangeEvidence(
        schema=AFFECTED_VERSION_RANGE_SCHEMA,
        finding_id=str(getattr(finding, "id", "")),
        ranges=ranges,
        observed_versions=observed,
        matching_versions=tuple(matching),
        outside_versions=tuple(outside),
        unparseable_ranges=tuple(unparseable),
        state=state,
        range_binding="single_cve",
        binding_ambiguity_reason=None,
        range_source=range_source,
        range_source_verified=range_source_verified,
        range_provenance_state=range_provenance_state,
        affected_version_supported=(state == "affected" and not unparseable),
        trusted_affected_version_supported=(
            state == "affected"
            and not unparseable
            and range_source_verified
        ),
        exploitability_confirmed=False,
    )
