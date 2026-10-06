from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .vulnerability_intelligence import finding_cve_ids


CVE_EVIDENCE_VERDICT_SCHEMA = "cve-evidence-verdict-v1"


@dataclass(frozen=True)
class CveEvidenceVerdict:
    schema: str
    finding_id: str
    cve_ids: tuple[str, ...]
    verdict: str
    confidence: str
    behavioral_evidence: bool
    version_evidence: bool
    high_confidence_version_evidence: bool
    ambiguity_reasons: tuple[str, ...]
    exploitability_confirmed: bool
    independent_validation_required: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cve_ids"] = list(self.cve_ids)
        payload["ambiguity_reasons"] = list(self.ambiguity_reasons)
        return payload


def build_cve_evidence_verdict(
    finding: Any,
    *,
    differential_signal: str = "none",
    versioned_fingerprint_match_count: int = 0,
    high_confidence_fingerprint_match_count: int = 0,
    ambiguity_reasons: Iterable[str] = (),
) -> CveEvidenceVerdict:
    cve_ids = finding_cve_ids(finding)
    versioned = max(0, int(versioned_fingerprint_match_count))
    high_confidence = max(0, int(high_confidence_fingerprint_match_count))
    reasons = tuple(
        sorted(
            {
                str(reason).strip()[:120]
                for reason in ambiguity_reasons
                if str(reason).strip()
            }
        )
    )
    behavioral = str(differential_signal).lower() == "strong"

    if not cve_ids:
        verdict = "not_a_cve_candidate"
        confidence = "none"
    elif reasons:
        verdict = "ambiguous_version_candidate"
        confidence = "low"
    elif behavioral and high_confidence > 0:
        verdict = "behaviorally_supported_cve_candidate"
        confidence = "high"
    elif high_confidence > 0:
        verdict = "high_confidence_version_candidate"
        confidence = "medium"
    elif versioned > 0:
        verdict = "version_candidate"
        confidence = "low"
    else:
        verdict = "identifier_only_candidate"
        confidence = "low"

    return CveEvidenceVerdict(
        schema=CVE_EVIDENCE_VERDICT_SCHEMA,
        finding_id=str(getattr(finding, "id", "")),
        cve_ids=cve_ids,
        verdict=verdict,
        confidence=confidence,
        behavioral_evidence=behavioral,
        version_evidence=versioned > 0,
        high_confidence_version_evidence=high_confidence > 0,
        ambiguity_reasons=reasons,
        exploitability_confirmed=False,
        independent_validation_required=True,
    )
