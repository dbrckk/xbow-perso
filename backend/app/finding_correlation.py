from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter

router = APIRouter()

_SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _canonical_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not parsed.scheme or not host:
        return value.strip().lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", ""))


@dataclass(frozen=True)
class FindingCorrelation:
    key: str
    finding_ids: tuple[str, ...]
    asset: str
    endpoint: str | None
    cwe: str | None
    highest_severity: str
    duplicate_candidate: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["finding_ids"] = list(self.finding_ids)
        return payload


def correlate_findings(findings: list[Any]) -> list[FindingCorrelation]:
    """Group likely duplicate findings without mutating or auto-merging them."""
    grouped: dict[tuple[str, str | None, str | None], list[Any]] = {}
    for finding in findings:
        asset = _canonical_url(str(finding.asset)) or str(finding.asset).strip().lower()
        endpoint = _canonical_url(finding.endpoint)
        cwe = str(finding.cwe).strip().upper() if finding.cwe else None
        grouped.setdefault((asset, endpoint, cwe), []).append(finding)

    correlations = []
    for (asset, endpoint, cwe), items in grouped.items():
        ordered = sorted(items, key=lambda item: str(item.id))
        highest = max(
            (str(item.severity) for item in ordered),
            key=lambda value: _SEVERITY_ORDER.get(value, -1),
        )
        key = "|".join((asset, endpoint or "-", cwe or "-"))
        correlations.append(
            FindingCorrelation(
                key=key,
                finding_ids=tuple(str(item.id) for item in ordered),
                asset=asset,
                endpoint=endpoint,
                cwe=cwe,
                highest_severity=highest,
                duplicate_candidate=len(ordered) > 1,
            )
        )

    return sorted(
        correlations,
        key=lambda item: (not item.duplicate_candidate, -_SEVERITY_ORDER.get(item.highest_severity, -1), item.key),
    )


@router.get("/api/campaigns/{campaign_id}/finding-correlations")
def campaign_finding_correlations(campaign_id: str):
    from .main import assert_campaign_exists

    campaign = assert_campaign_exists(campaign_id)
    correlations = correlate_findings(campaign.findings)
    duplicate_groups = [item for item in correlations if item.duplicate_candidate]
    duplicate_findings = sum(len(item.finding_ids) for item in duplicate_groups)
    return {
        "campaign_id": campaign.id,
        "correlations": [item.to_dict() for item in correlations],
        "summary": {
            "groups": len(correlations),
            "duplicate_groups": len(duplicate_groups),
            "findings_in_duplicate_groups": duplicate_findings,
        },
        "read_only": True,
        "auto_merge": False,
    }
