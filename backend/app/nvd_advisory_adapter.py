from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


NVD_ADVISORY_ADAPTER_SCHEMA = "nvd-advisory-adapter-v1"
_CVE_RE = re.compile(r"^CVE-(\d{4})-(\d{4,10})$", re.IGNORECASE)
_MAX_VULNERABILITIES = 10000
_MAX_CONFIGURATIONS_PER_CVE = 64
_MAX_MATCHES_PER_NODE = 128
_MAX_OUTPUT_ENTRIES = 20000


class NvdAdvisoryAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class NvdAdvisoryAdapterResult:
    schema: str
    document: dict[str, Any]
    input_vulnerability_count: int
    output_entry_count: int
    skipped_complex_configurations: int
    skipped_non_vulnerable_matches: int
    skipped_unusable_version_matches: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "document": self.document,
            "input_vulnerability_count": self.input_vulnerability_count,
            "output_entry_count": self.output_entry_count,
            "skipped_complex_configurations": self.skipped_complex_configurations,
            "skipped_non_vulnerable_matches": self.skipped_non_vulnerable_matches,
            "skipped_unusable_version_matches": self.skipped_unusable_version_matches,
        }


def _text(value: object, *, name: str, max_len: int = 256) -> str:
    if not isinstance(value, str):
        raise NvdAdvisoryAdapterError(f"{name} must be text")
    result = value.strip()
    if (
        not result
        or len(result) > max_len
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in result)
    ):
        raise NvdAdvisoryAdapterError(f"{name} is invalid")
    return result


def _parse_cpe23(criteria: object) -> tuple[str, str, str] | None:
    try:
        raw = _text(criteria, name="criteria", max_len=1024)
    except NvdAdvisoryAdapterError:
        return None
    if not raw.startswith("cpe:2.3:"):
        return None
    parts = raw.split(":")
    if len(parts) != 13:
        return None
    vendor = parts[3].strip().lower()
    product = parts[4].strip().lower()
    version = parts[5].strip()
    if vendor in {"", "*", "-"} or product in {"", "*", "-"}:
        return None
    return vendor, product, version


def _numeric_version(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split(".")
    if not 1 <= len(parts) <= 6:
        return None
    if any(not part.isdigit() for part in parts):
        return None
    return ".".join(str(int(part)) for part in parts)


def _range_expression(match: Mapping[str, Any], cpe_version: str) -> str | None:
    clauses: list[str] = []

    bounds = (
        ("versionStartIncluding", ">="),
        ("versionStartExcluding", ">"),
        ("versionEndIncluding", "<="),
        ("versionEndExcluding", "<"),
    )
    for field, operator in bounds:
        if field not in match:
            continue
        version = _numeric_version(match.get(field))
        if version is None:
            return None
        clauses.append(f"{operator}{version}")

    if clauses:
        return ",".join(clauses)

    exact = _numeric_version(cpe_version)
    if exact is not None:
        return f"={exact}"

    return None


def _simple_cpe_matches(
    configuration: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]] | None, bool]:
    nodes = configuration.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 1:
        return None, False

    node = nodes[0]
    if not isinstance(node, Mapping):
        return None, False
    if node.get("negate") is True:
        return None, False
    if str(node.get("operator") or "OR").upper() != "OR":
        return None, False
    if node.get("children"):
        return None, False

    matches = node.get("cpeMatch")
    if not isinstance(matches, list):
        return None, False
    if len(matches) > _MAX_MATCHES_PER_NODE:
        raise NvdAdvisoryAdapterError(
            "NVD configuration exceeds CPE match limit"
        )
    if any(not isinstance(item, Mapping) for item in matches):
        raise NvdAdvisoryAdapterError(
            "NVD CPE match must be an object"
        )
    return list(matches), True


def adapt_nvd_cve_api_v2(document: Mapping[str, Any]) -> NvdAdvisoryAdapterResult:
    if not isinstance(document, Mapping):
        raise NvdAdvisoryAdapterError("NVD document must be an object")

    raw_vulnerabilities = document.get("vulnerabilities")
    if not isinstance(raw_vulnerabilities, list):
        raise NvdAdvisoryAdapterError(
            "NVD vulnerabilities must be a list"
        )
    if len(raw_vulnerabilities) > _MAX_VULNERABILITIES:
        raise NvdAdvisoryAdapterError(
            "NVD vulnerability count exceeds limit"
        )

    output: dict[tuple[str, str, str], set[str]] = {}
    skipped_complex = 0
    skipped_non_vulnerable = 0
    skipped_unusable = 0

    for raw_wrapper in raw_vulnerabilities:
        if not isinstance(raw_wrapper, Mapping):
            raise NvdAdvisoryAdapterError(
                "NVD vulnerability wrapper must be an object"
            )
        cve = raw_wrapper.get("cve")
        if not isinstance(cve, Mapping):
            raise NvdAdvisoryAdapterError(
                "NVD vulnerability cve must be an object"
            )
        cve_id = _text(cve.get("id"), name="cve.id", max_len=32).upper()
        if not _CVE_RE.fullmatch(cve_id):
            raise NvdAdvisoryAdapterError("NVD CVE id is invalid")

        configurations = cve.get("configurations") or []
        if not isinstance(configurations, list):
            raise NvdAdvisoryAdapterError(
                "NVD configurations must be a list"
            )
        if len(configurations) > _MAX_CONFIGURATIONS_PER_CVE:
            raise NvdAdvisoryAdapterError(
                "NVD configuration count exceeds limit"
            )

        for configuration in configurations:
            if not isinstance(configuration, Mapping):
                raise NvdAdvisoryAdapterError(
                    "NVD configuration must be an object"
                )
            matches, simple = _simple_cpe_matches(configuration)
            if not simple or matches is None:
                skipped_complex += 1
                continue

            for match in matches:
                if match.get("vulnerable") is not True:
                    skipped_non_vulnerable += 1
                    continue
                identity = _parse_cpe23(match.get("criteria"))
                if identity is None:
                    skipped_unusable += 1
                    continue
                vendor, product, cpe_version = identity
                expression = _range_expression(match, cpe_version)
                if expression is None:
                    skipped_unusable += 1
                    continue

                key = (cve_id, vendor, product)
                output.setdefault(key, set()).add(expression)
                if len(output) > _MAX_OUTPUT_ENTRIES:
                    raise NvdAdvisoryAdapterError(
                        "NVD adapter output exceeds entry limit"
                    )

    entries = [
        {
            "cve_id": cve_id,
            "vendor": vendor,
            "product": product,
            "affected_version_ranges": sorted(ranges),
        }
        for (cve_id, vendor, product), ranges in sorted(output.items())
    ]
    normalized = {
        "count": len(entries),
        "entries": entries,
    }
    return NvdAdvisoryAdapterResult(
        schema=NVD_ADVISORY_ADAPTER_SCHEMA,
        document=normalized,
        input_vulnerability_count=len(raw_vulnerabilities),
        output_entry_count=len(entries),
        skipped_complex_configurations=skipped_complex,
        skipped_non_vulnerable_matches=skipped_non_vulnerable,
        skipped_unusable_version_matches=skipped_unusable,
    )
