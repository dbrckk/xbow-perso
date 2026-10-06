from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VALIDATION_PRIORITY_SCHEMA = "validation-priority-v1"

_SEVERITY_WEIGHT = {
    "info": 0.05,
    "low": 0.15,
    "medium": 0.40,
    "high": 0.75,
    "critical": 1.00,
}

_CVE_VERDICT_WEIGHT = {
    "not_a_cve_candidate": 0.00,
    "identifier_only_candidate": 0.15,
    "version_candidate": 0.35,
    "high_confidence_version_candidate": 0.60,
    "behaviorally_supported_cve_candidate": 0.90,
    "ambiguous_version_candidate": 0.10,
}


@dataclass(frozen=True)
class ValidationPriority:
    schema: str
    finding_id: str
    score: float
    band: str
    recommended_state: str
    reasons: tuple[str, ...]
    non_destructive_only: bool
    automatic_execution_authorized: bool
    independent_validation_required: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def build_validation_priority(
    finding: Any,
    *,
    cve_verdict: Any,
    vulnerability_signal: Any,
    differential_signal: str = "none",
    triage_score: float = 0.0,
    cve_risk_score: float = 0.0,
    duplicate_candidate: bool = False,
    cluster_saturated: bool = False,
) -> ValidationPriority:
    finding_id = str(getattr(finding, "id", ""))
    status = str(getattr(finding, "status", ""))
    severity = str(getattr(finding, "severity", "")).lower()
    severity_weight = _SEVERITY_WEIGHT.get(severity, 0.0)

    verdict = str(_field(cve_verdict, "verdict", "not_a_cve_candidate"))
    cve_weight = _CVE_VERDICT_WEIGHT.get(verdict, 0.0)
    ambiguity = tuple(_field(cve_verdict, "ambiguity_reasons", ()) or ())

    novel_candidate = bool(_field(vulnerability_signal, "novel_candidate", False))
    known_cve_candidate = bool(
        _field(vulnerability_signal, "known_cve_candidate", False)
    )

    differential = str(differential_signal).lower()
    differential_weight = 0.15 if differential == "strong" else 0.07 if differential == "weak" else 0.0

    try:
        triage = max(0.0, min(1.0, float(triage_score)))
    except (TypeError, ValueError):
        triage = 0.0
    try:
        cve_risk = max(0.0, min(1.0, float(cve_risk_score)))
    except (TypeError, ValueError):
        cve_risk = 0.0

    score = (
        severity_weight * 0.40
        + cve_weight * 0.30
        + differential_weight
        + triage * 0.15
        + cve_risk * 0.10
    )
    if novel_candidate:
        score += 0.12
    if ambiguity:
        score -= 0.10
    if duplicate_candidate:
        score -= 0.08
    if cluster_saturated:
        score -= 0.20
    score = round(max(0.0, min(1.0, score)), 4)

    reasons: list[str] = []
    if severity in {"high", "critical"}:
        reasons.append("high_impact")
    if known_cve_candidate:
        reasons.append("known_cve_candidate")
    if cve_risk >= 0.75:
        reasons.append("high_cve_risk_context")
    elif cve_risk >= 0.55:
        reasons.append("elevated_cve_risk_context")
    if novel_candidate:
        reasons.append("corroborated_unknown_candidate")
    if differential == "strong":
        reasons.append("strong_behavioral_signal")
    if verdict == "high_confidence_version_candidate":
        reasons.append("high_confidence_version_evidence")
    if verdict == "behaviorally_supported_cve_candidate":
        reasons.append("behaviorally_supported_cve")
    if ambiguity:
        reasons.append("version_ambiguity")
    if duplicate_candidate:
        reasons.append("duplicate_candidate")
    if cluster_saturated:
        reasons.append("cluster_validation_saturated")

    if status in {"confirmed", "rejected"}:
        band = "resolved"
        recommended = "no_action"
    elif cluster_saturated:
        band = "deferred"
        recommended = "defer_duplicate_validation"
    elif ambiguity:
        band = "review"
        recommended = "passive_review"
    elif score >= 0.70:
        band = "urgent"
        recommended = "safe_active_validation"
    elif score >= 0.45:
        band = "high"
        recommended = "safe_active_validation"
    elif score >= 0.25:
        band = "medium"
        recommended = "passive_review"
    else:
        band = "low"
        recommended = "defer_low_signal"

    return ValidationPriority(
        schema=VALIDATION_PRIORITY_SCHEMA,
        finding_id=finding_id,
        score=score,
        band=band,
        recommended_state=recommended,
        reasons=tuple(reasons),
        non_destructive_only=True,
        automatic_execution_authorized=False,
        independent_validation_required=True,
    )
