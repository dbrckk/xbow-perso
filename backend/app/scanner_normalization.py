from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

from .main import Campaign, Finding, is_host_allowed


_ALLOWED_SEVERITIES = {"info", "low", "medium", "high", "critical"}


@dataclass(frozen=True)
class NormalizedScannerFinding:
    engine: str
    title: str
    severity: str
    asset: str
    endpoint: str | None
    summary: str
    evidence: tuple[str, ...] = ()
    reproduction_steps: tuple[str, ...] = ()
    impact: str = ""
    remediation: str = ""
    cwe: str | None = None
    cvss: float | None = None
    template_id: str | None = None
    matcher_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        payload["reproduction_steps"] = list(self.reproduction_steps)
        return payload


def _optional_str(value: Any) -> str | None:
    return None if value in {None, ""} else str(value)


def _optional_cvss(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 10 else None


def _severity(value: Any) -> str:
    normalized = str(value or "info").lower().strip()
    return normalized if normalized in _ALLOWED_SEVERITIES else "info"


def _string_list(value: Any, *, limit: int = 50) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]
    return tuple(str(item) for item in items[:limit])


def normalize_strix_item(item: dict[str, Any], campaign: Campaign) -> NormalizedScannerFinding | None:
    asset = str(item.get("asset") or item.get("target") or campaign.target.primary_url)
    host = (urlparse(asset).hostname or asset.split(":")[0]).lower()
    if not is_host_allowed(host, campaign.target.rules.allowed_targets, campaign.target.rules.denied_targets):
        return None

    cwe = item.get("cwe")
    if isinstance(cwe, list):
        cwe = ", ".join(str(x) for x in cwe)

    return NormalizedScannerFinding(
        engine="strix",
        title=str(item.get("title") or item.get("name") or "Strix finding"),
        severity=_severity(item.get("severity")),
        asset=asset,
        endpoint=_optional_str(item.get("endpoint")),
        summary=str(item.get("summary") or item.get("description") or item.get("technical_analysis") or ""),
        evidence=_string_list(item.get("evidence")),
        reproduction_steps=_string_list(
            item.get("reproduction_steps")
            or item.get("poc_steps")
            or item.get("poc_description")
        ),
        impact=str(item.get("impact") or ""),
        remediation=str(item.get("remediation") or item.get("recommendation") or ""),
        cwe=_optional_str(cwe),
        cvss=_optional_cvss(item.get("cvss")),
    )


def normalize_nuclei_item(item: dict[str, Any], campaign: Campaign) -> NormalizedScannerFinding | None:
    matched_at = str(item.get("matched-at") or item.get("matched_at") or item.get("url") or "")
    host = (urlparse(matched_at).hostname or "").lower()
    if not matched_at or not host:
        return None
    if not is_host_allowed(host, campaign.target.rules.allowed_targets, campaign.target.rules.denied_targets):
        return None

    info = item.get("info") if isinstance(item.get("info"), dict) else {}
    classification = info.get("classification") if isinstance(info.get("classification"), dict) else {}
    cwe = classification.get("cwe-id") or classification.get("cwe_id")
    if isinstance(cwe, list):
        cwe = ", ".join(str(x) for x in cwe)

    extracted = item.get("extracted-results") or item.get("extracted_results") or []
    matcher = item.get("matcher-name") or item.get("matcher_name")
    template_id = item.get("template-id") or item.get("template_id")

    return NormalizedScannerFinding(
        engine="nuclei",
        title=str(info.get("name") or template_id or "Nuclei finding"),
        severity=_severity(info.get("severity")),
        asset=f"{urlparse(matched_at).scheme}://{host}",
        endpoint=matched_at,
        summary=str(info.get("description") or ""),
        evidence=_string_list(extracted),
        reproduction_steps=(),
        impact="",
        remediation=str(info.get("remediation") or info.get("reference") or ""),
        cwe=_optional_str(cwe),
        cvss=_optional_cvss(
            classification.get("cvss-score")
            or classification.get("cvss_score")
        ),
        template_id=_optional_str(template_id),
        matcher_name=_optional_str(matcher),
    )


def normalized_finding_id(item: NormalizedScannerFinding) -> str:
    canonical = json.dumps(
        [
            item.engine,
            item.title.strip(),
            item.asset.strip(),
            item.endpoint or "",
            item.cwe or "",
            item.summary.strip(),
            item.template_id or "",
            item.matcher_name or "",
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{item.engine}-{digest[:32]}"


def to_campaign_finding(item: NormalizedScannerFinding) -> Finding:
    return Finding(
        id=normalized_finding_id(item),
        title=item.title,
        severity=item.severity,
        asset=item.asset,
        endpoint=item.endpoint,
        summary=item.summary,
        evidence=list(item.evidence),
        reproduction_steps=list(item.reproduction_steps),
        impact=item.impact,
        remediation=item.remediation,
        cwe=item.cwe,
        cvss=item.cvss,
        status="validation_required",
        discovered_by=item.engine,
    )


def dedupe_normalized(items: Iterable[NormalizedScannerFinding]) -> list[NormalizedScannerFinding]:
    seen: set[str] = set()
    result: list[NormalizedScannerFinding] = []
    for item in items:
        finding_id = normalized_finding_id(item)
        if finding_id in seen:
            continue
        seen.add(finding_id)
        result.append(item)
    return result
