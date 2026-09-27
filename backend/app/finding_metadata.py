from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any

_CWE_RE = re.compile(r"^CWE-[1-9][0-9]{0,5}$")

_CVSS_RANGES = (
    (0.0, 0.0, "none"),
    (0.1, 3.9, "low"),
    (4.0, 6.9, "medium"),
    (7.0, 8.9, "high"),
    (9.0, 10.0, "critical"),
)


def normalize_cwe(value: Any) -> str | None:
    """Return canonical CWE-N form when the supplied value is valid."""
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if not _CWE_RE.fullmatch(normalized):
        return None
    return normalized


def normalize_cvss_score(value: Any) -> float | None:
    """Return a finite CVSS base score in the valid 0.0..10.0 range."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 10.0:
        return None
    return score


def cvss_qualitative_rating(value: Any) -> str | None:
    """Map a valid CVSS v3.x base score to its qualitative severity band."""
    score = normalize_cvss_score(value)
    if score is None:
        return None
    for lower, upper, label in _CVSS_RANGES:
        if lower <= score <= upper:
            return label
    return None


def severity_matches_cvss(severity: Any, value: Any) -> bool:
    """Check declared severity against the CVSS qualitative rating."""
    rating = cvss_qualitative_rating(value)
    if rating is None:
        return False
    declared = str(severity or "").strip().lower()
    if rating == "none":
        return declared == "info"
    return declared == rating


@dataclass(frozen=True)
class FindingMetadataAssessment:
    canonical_cwe: str | None
    cwe_valid: bool
    cvss_score: float | None
    cvss_rating: str | None
    severity_cvss_consistent: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_finding_metadata(finding: Any) -> FindingMetadataAssessment:
    canonical_cwe = normalize_cwe(getattr(finding, "cwe", None))
    score = normalize_cvss_score(getattr(finding, "cvss", None))
    rating = cvss_qualitative_rating(score)
    return FindingMetadataAssessment(
        canonical_cwe=canonical_cwe,
        cwe_valid=canonical_cwe is not None,
        cvss_score=score,
        cvss_rating=rating,
        severity_cvss_consistent=severity_matches_cvss(
            getattr(finding, "severity", None),
            score,
        ),
    )
