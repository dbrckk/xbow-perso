from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


CVE_VALIDATION_PRIORITY_SCHEMA = "cve-validation-priority-v1"
_SEVERITY_WEIGHT = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


@dataclass(frozen=True)
class CveValidationPriority:
    schema: str
    finding_id: str
    priority_score: int
    priority_band: str
    validation_mode: str
    reasons: tuple[str, ...]
    recommended_checks: tuple[str, ...]
    destructive_testing_allowed: bool
    state_changing_validation_allowed: bool
    exploit_execution_allowed: bool
    independent_validation_required: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["recommended_checks"] = list(self.recommended_checks)
        return payload


def _bounded_probability(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 1:
        return score
    return None


def build_cve_validation_priority(
    finding: Any,
    *,
    verdict: Any,
    corroborating_source_count: int = 0,
    ambiguity_reasons: Iterable[str] = (),
) -> CveValidationPriority:
    finding_id = str(getattr(finding, "id", ""))
    severity = str(getattr(finding, "severity", "")).lower()
    severity_weight = _SEVERITY_WEIGHT.get(severity, 0)
    epss = _bounded_probability(getattr(finding, "epss_score", None))
    verdict_name = str(getattr(verdict, "verdict", ""))
    behavioral = bool(getattr(verdict, "behavioral_evidence", False))
    version = bool(getattr(verdict, "version_evidence", False))
    high_version = bool(
        getattr(verdict, "high_confidence_version_evidence", False)
    )
    reasons = {
        str(reason).strip()[:120]
        for reason in ambiguity_reasons
        if str(reason).strip()
    }
    reasons.update(
        str(reason).strip()[:120]
        for reason in getattr(verdict, "ambiguity_reasons", ())
        if str(reason).strip()
    )

    score = severity_weight * 12
    rationale: list[str] = []

    if verdict_name == "behaviorally_supported_cve_candidate":
        score += 30
        rationale.append("behavioral_support")
    elif high_version:
        score += 18
        rationale.append("high_confidence_version")
    elif version:
        score += 10
        rationale.append("version_correlation")
    elif verdict_name == "identifier_only_candidate":
        rationale.append("identifier_only")

    sources = max(0, int(corroborating_source_count))
    if sources >= 2:
        score += 12
        rationale.append("independent_scanner_corroboration")

    if epss is not None:
        if epss >= 0.5:
            score += 12
            rationale.append("high_epss")
        elif epss >= 0.1:
            score += 6
            rationale.append("elevated_epss")

    if reasons:
        score -= 20
        rationale.append("version_ambiguity")

    score = max(0, min(100, score))

    if reasons:
        validation_mode = "passive_recheck"
        recommended = (
            "re_fingerprint_product_and_version",
            "check_package_or_build_metadata",
            "compare_behavior_against_known_safe_baseline",
        )
    elif behavioral and high_version:
        validation_mode = "safe_active"
        recommended = (
            "reproduce_non_destructive_behavior",
            "capture_request_response_digests",
            "independent_validator_recheck",
        )
    elif high_version or version:
        validation_mode = "safe_active"
        recommended = (
            "verify_exact_product_and_version",
            "run_non_destructive_template_validation",
            "capture_request_response_digests",
        )
    else:
        validation_mode = "passive_recheck"
        recommended = (
            "verify_cve_metadata",
            "verify_product_identity",
            "verify_version_evidence",
        )

    if score >= 70:
        band = "urgent"
    elif score >= 45:
        band = "high"
    elif score >= 20:
        band = "normal"
    else:
        band = "low"

    return CveValidationPriority(
        schema=CVE_VALIDATION_PRIORITY_SCHEMA,
        finding_id=finding_id,
        priority_score=score,
        priority_band=band,
        validation_mode=validation_mode,
        reasons=tuple(sorted(set(rationale))),
        recommended_checks=recommended,
        destructive_testing_allowed=False,
        state_changing_validation_allowed=False,
        exploit_execution_allowed=False,
        independent_validation_required=True,
    )
