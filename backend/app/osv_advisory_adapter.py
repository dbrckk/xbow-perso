from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


OSV_ADVISORY_ADAPTER_SCHEMA = "osv-advisory-adapter-v1"
_CVE_RE = re.compile(r"^CVE-(\d{4})-(\d{4,10})$", re.IGNORECASE)
_NUMERIC_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,5}$")
_MAX_RECORDS = 10000
_MAX_AFFECTED = 256
_MAX_RANGES_PER_AFFECTED = 64
_MAX_EVENTS_PER_RANGE = 128
_MAX_VERSIONS_PER_AFFECTED = 2048
_MAX_OUTPUT_ENTRIES = 20000
_MAX_OUTPUT_RANGES = 16


class OsvAdvisoryAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class OsvAdvisoryAdapterResult:
    schema: str
    document: dict[str, Any]
    input_record_count: int
    output_entry_count: int
    skipped_ambiguous_cve_bindings: int
    skipped_non_semver_ranges: int
    skipped_unusable_semver_ranges: int
    skipped_unusable_explicit_versions: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "document": self.document,
            "input_record_count": self.input_record_count,
            "output_entry_count": self.output_entry_count,
            "skipped_ambiguous_cve_bindings": (
                self.skipped_ambiguous_cve_bindings
            ),
            "skipped_non_semver_ranges": self.skipped_non_semver_ranges,
            "skipped_unusable_semver_ranges": (
                self.skipped_unusable_semver_ranges
            ),
            "skipped_unusable_explicit_versions": (
                self.skipped_unusable_explicit_versions
            ),
        }


def _text(
    value: object,
    *,
    name: str,
    max_len: int,
) -> str:
    if not isinstance(value, str):
        raise OsvAdvisoryAdapterError(f"{name} must be text")
    result = value.strip()
    if (
        not result
        or len(result) > max_len
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in result)
    ):
        raise OsvAdvisoryAdapterError(f"{name} is invalid")
    return result


def _numeric_version(value: object) -> str | None:
    raw = str(value or "").strip()
    if not _NUMERIC_VERSION_RE.fullmatch(raw):
        return None
    return ".".join(str(int(part)) for part in raw.split("."))


def _record_cve_id(record: Mapping[str, Any]) -> str | None:
    candidates: set[str] = set()
    record_id = record.get("id")
    if isinstance(record_id, str) and _CVE_RE.fullmatch(record_id.strip()):
        candidates.add(record_id.strip().upper())

    aliases = record.get("aliases") or []
    if aliases:
        if not isinstance(aliases, list):
            raise OsvAdvisoryAdapterError("OSV aliases must be a list")
        for alias in aliases[:128]:
            if isinstance(alias, str) and _CVE_RE.fullmatch(alias.strip()):
                candidates.add(alias.strip().upper())

    if len(candidates) != 1:
        return None
    return next(iter(candidates))


def _expression(start: str | None, end_op: str | None, end: str | None) -> str:
    clauses: list[str] = []
    if start is not None and start != "0":
        clauses.append(f">={start}")
    elif start == "0":
        clauses.append(">=0")
    if end_op is not None and end is not None:
        clauses.append(f"{end_op}{end}")
    return ",".join(clauses)


def _semver_event_ranges(events: object) -> tuple[str, ...] | None:
    if not isinstance(events, list) or not 1 <= len(events) <= _MAX_EVENTS_PER_RANGE:
        return None

    open_range = False
    start: str | None = None
    expressions: list[str] = []
    saw_introduced = False
    saw_fixed = False
    saw_last_affected = False

    for raw_event in events:
        if not isinstance(raw_event, Mapping):
            return None
        supported_keys = [
            key
            for key in ("introduced", "fixed", "last_affected", "limit")
            if key in raw_event
        ]
        if len(supported_keys) != 1 or len(raw_event) != 1:
            return None

        key = supported_keys[0]
        raw_value = raw_event.get(key)

        if key == "introduced":
            if open_range:
                return None
            value = str(raw_value or "").strip()
            if value == "0":
                start = "0"
            else:
                start = _numeric_version(value)
                if start is None:
                    return None
            open_range = True
            saw_introduced = True
            continue

        if not open_range:
            return None

        if key == "fixed":
            if saw_last_affected:
                return None
            value = _numeric_version(raw_value)
            if value is None:
                return None
            expressions.append(_expression(start, "<", value))
            open_range = False
            start = None
            saw_fixed = True
            continue

        if key == "last_affected":
            if saw_fixed:
                return None
            value = _numeric_version(raw_value)
            if value is None:
                return None
            expressions.append(_expression(start, "<=", value))
            open_range = False
            start = None
            saw_last_affected = True
            continue

        value = str(raw_value or "").strip()
        if value == "*":
            expressions.append(_expression(start, None, None))
        else:
            numeric_limit = _numeric_version(value)
            if numeric_limit is None:
                return None
            expressions.append(_expression(start, "<", numeric_limit))
        open_range = False
        start = None

    if not saw_introduced:
        return None
    if open_range:
        expressions.append(_expression(start, None, None))

    normalized = tuple(
        expression
        for expression in expressions
        if expression
    )
    return normalized or None


def _records(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if "id" in document and "affected" in document:
        return [document]

    raw_records = document.get("vulns")
    if not isinstance(raw_records, list):
        raise OsvAdvisoryAdapterError(
            "OSV document must be one vulnerability or a vuln bundle"
        )
    if len(raw_records) > _MAX_RECORDS:
        raise OsvAdvisoryAdapterError("OSV record count exceeds limit")
    if any(not isinstance(item, Mapping) for item in raw_records):
        raise OsvAdvisoryAdapterError("OSV vuln bundle contains non-object")
    return list(raw_records)


def adapt_osv_v1(document: Mapping[str, Any]) -> OsvAdvisoryAdapterResult:
    if not isinstance(document, Mapping):
        raise OsvAdvisoryAdapterError("OSV document must be an object")

    records = _records(document)
    if len(records) > _MAX_RECORDS:
        raise OsvAdvisoryAdapterError("OSV record count exceeds limit")

    output: dict[tuple[str, str, str], set[str]] = {}
    skipped_ambiguous = 0
    skipped_non_semver = 0
    skipped_semver = 0
    skipped_versions = 0

    for record in records:
        cve_id = _record_cve_id(record)
        if cve_id is None:
            skipped_ambiguous += 1
            continue

        affected = record.get("affected") or []
        if not isinstance(affected, list):
            raise OsvAdvisoryAdapterError("OSV affected must be a list")
        if len(affected) > _MAX_AFFECTED:
            raise OsvAdvisoryAdapterError(
                "OSV affected package count exceeds limit"
            )

        for raw_affected in affected:
            if not isinstance(raw_affected, Mapping):
                raise OsvAdvisoryAdapterError(
                    "OSV affected entry must be an object"
                )
            package = raw_affected.get("package")
            if not isinstance(package, Mapping):
                raise OsvAdvisoryAdapterError(
                    "OSV affected package must be an object"
                )
            ecosystem = _text(
                package.get("ecosystem"),
                name="OSV package ecosystem",
                max_len=120,
            ).lower()
            package_name = _text(
                package.get("name"),
                name="OSV package name",
                max_len=240,
            )

            ranges: set[str] = set()
            raw_ranges = raw_affected.get("ranges") or []
            if not isinstance(raw_ranges, list):
                raise OsvAdvisoryAdapterError(
                    "OSV affected ranges must be a list"
                )
            if len(raw_ranges) > _MAX_RANGES_PER_AFFECTED:
                raise OsvAdvisoryAdapterError(
                    "OSV affected range count exceeds limit"
                )

            for raw_range in raw_ranges:
                if not isinstance(raw_range, Mapping):
                    raise OsvAdvisoryAdapterError(
                        "OSV range must be an object"
                    )
                range_type = str(raw_range.get("type") or "").strip().upper()
                if range_type != "SEMVER":
                    skipped_non_semver += 1
                    continue
                converted = _semver_event_ranges(raw_range.get("events"))
                if converted is None:
                    skipped_semver += 1
                    continue
                ranges.update(converted)

            versions = raw_affected.get("versions") or []
            if not isinstance(versions, list):
                raise OsvAdvisoryAdapterError(
                    "OSV affected versions must be a list"
                )
            if len(versions) > _MAX_VERSIONS_PER_AFFECTED:
                raise OsvAdvisoryAdapterError(
                    "OSV affected versions exceed limit"
                )
            for raw_version in versions:
                version = _numeric_version(raw_version)
                if version is None:
                    skipped_versions += 1
                    continue
                ranges.add(f"={version}")

            if not ranges:
                continue
            if len(ranges) > _MAX_OUTPUT_RANGES:
                raise OsvAdvisoryAdapterError(
                    "OSV package produces too many affected ranges"
                )

            key = (cve_id, ecosystem, package_name)
            output.setdefault(key, set()).update(ranges)
            if len(output) > _MAX_OUTPUT_ENTRIES:
                raise OsvAdvisoryAdapterError(
                    "OSV adapter output exceeds entry limit"
                )
            if len(output[key]) > _MAX_OUTPUT_RANGES:
                raise OsvAdvisoryAdapterError(
                    "OSV package produces too many affected ranges"
                )

    entries = [
        {
            "cve_id": cve_id,
            "package_ecosystem": ecosystem,
            "package_name": package_name,
            "affected_version_ranges": sorted(ranges),
        }
        for (cve_id, ecosystem, package_name), ranges in sorted(output.items())
    ]
    normalized = {
        "count": len(entries),
        "entries": entries,
    }
    return OsvAdvisoryAdapterResult(
        schema=OSV_ADVISORY_ADAPTER_SCHEMA,
        document=normalized,
        input_record_count=len(records),
        output_entry_count=len(entries),
        skipped_ambiguous_cve_bindings=skipped_ambiguous,
        skipped_non_semver_ranges=skipped_non_semver,
        skipped_unusable_semver_ranges=skipped_semver,
        skipped_unusable_explicit_versions=skipped_versions,
    )
