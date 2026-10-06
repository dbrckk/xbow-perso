from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from .kev_catalog import finding_has_authoritative_kev

if TYPE_CHECKING:
    from .kev_catalog import KevCatalog

from .vulnerability_intelligence import finding_cve_ids


CVE_RISK_CONTEXT_SCHEMA = "cve-risk-context-v1"


@dataclass(frozen=True)
class CveRiskContext:
    schema: str
    finding_id: str
    cve_ids: tuple[str, ...]
    cvss: float | None
    epss_score: float | None
    epss_percentile: float | None
    cpe_present: bool
    template_verified: bool
    scanner_tagged_kev: bool
    authoritative_kev_verified: bool
    risk_score: float
    risk_band: str
    reasons: tuple[str, ...]
    exploitability_confirmed: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cve_ids"] = list(self.cve_ids)
        payload["reasons"] = list(self.reasons)
        return payload


def _unit_interval(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= result <= 1.0:
        return None
    return result


def _cvss(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= result <= 10.0:
        return None
    return result


def build_cve_risk_context(
    finding: Any,
    *,
    authoritative_kev_verified: bool = False,
    kev_catalog: "KevCatalog | None" = None,
) -> CveRiskContext:
    cve_ids = finding_cve_ids(finding)
    cvss = _cvss(getattr(finding, "cvss", None))
    epss_score = _unit_interval(getattr(finding, "epss_score", None))
    epss_percentile = _unit_interval(
        getattr(finding, "epss_percentile", None)
    )
    cpe = getattr(finding, "cpe", None)
    cpe_present = bool(
        isinstance(cpe, (list, tuple, set))
        and any(str(item).strip() for item in cpe)
    )
    template_verified = getattr(finding, "template_verified", None) is True
    tags = {
        str(tag).strip().lower()
        for tag in (getattr(finding, "tags", None) or ())
        if str(tag).strip()
    }
    scanner_tagged_kev = "kev" in tags
    catalog_authoritative = bool(
        kev_catalog is not None
        and finding_has_authoritative_kev(kev_catalog, cve_ids)
    )
    authoritative = bool(
        authoritative_kev_verified or catalog_authoritative
    )

    if not cve_ids:
        return CveRiskContext(
            schema=CVE_RISK_CONTEXT_SCHEMA,
            finding_id=str(getattr(finding, "id", "")),
            cve_ids=(),
            cvss=cvss,
            epss_score=epss_score,
            epss_percentile=epss_percentile,
            cpe_present=cpe_present,
            template_verified=template_verified,
            scanner_tagged_kev=scanner_tagged_kev,
            authoritative_kev_verified=False,
            risk_score=0.0,
            risk_band="not_applicable",
            reasons=(),
            exploitability_confirmed=False,
        )

    score = 0.0
    reasons: list[str] = []

    if cvss is not None:
        score += (cvss / 10.0) * 0.35
        if cvss >= 9.0:
            reasons.append("critical_cvss")
        elif cvss >= 7.0:
            reasons.append("high_cvss")

    if epss_score is not None:
        score += epss_score * 0.20
        if epss_score >= 0.50:
            reasons.append("high_epss_score")

    if epss_percentile is not None:
        score += epss_percentile * 0.25
        if epss_percentile >= 0.90:
            reasons.append("high_epss_percentile")

    if cpe_present:
        score += 0.05
        reasons.append("cpe_present")

    if template_verified:
        score += 0.05
        reasons.append("verified_template")

    if authoritative:
        score += 0.20
        reasons.append("authoritative_kev_verified")
    elif scanner_tagged_kev:
        score += 0.08
        reasons.append("scanner_tagged_kev_unverified")

    score = round(max(0.0, min(1.0, score)), 4)
    if score >= 0.75:
        band = "critical_priority"
    elif score >= 0.55:
        band = "high_priority"
    elif score >= 0.30:
        band = "medium_priority"
    else:
        band = "low_priority"

    return CveRiskContext(
        schema=CVE_RISK_CONTEXT_SCHEMA,
        finding_id=str(getattr(finding, "id", "")),
        cve_ids=cve_ids,
        cvss=cvss,
        epss_score=epss_score,
        epss_percentile=epss_percentile,
        cpe_present=cpe_present,
        template_verified=template_verified,
        scanner_tagged_kev=scanner_tagged_kev,
        authoritative_kev_verified=authoritative,
        risk_score=score,
        risk_band=band,
        reasons=tuple(reasons),
        exploitability_confirmed=False,
    )
