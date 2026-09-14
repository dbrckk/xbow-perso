from __future__ import annotations

import re
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
    """Group likely duplicates conservatively without auto-merging records."""
    grouped: dict[tuple[str, str | None, str | None, str | None], list[Any]] = {}
    for finding in findings:
        asset = _canonical_url(str(finding.asset)) or str(finding.asset).strip().lower()
        endpoint = _canonical_url(finding.endpoint)
        cwe = str(finding.cwe).strip().upper() if finding.cwe else None
        title = str(finding.title).strip().lower() if finding.title else None
        strong_identity = cwe or title
        grouped.setdefault((asset, endpoint, cwe, strong_identity), []).append(finding)

    correlations = []
    for (asset, endpoint, cwe, strong_identity), items in grouped.items():
        ordered = sorted(items, key=lambda item: str(item.id))
        highest = max(
            (str(item.severity) for item in ordered),
            key=lambda value: _SEVERITY_ORDER.get(value, -1),
        )
        key = "|".join((asset, endpoint or "-", cwe or "-", strong_identity or "-"))
        duplicate_candidate = len(ordered) > 1 and bool(endpoint or cwe)
        correlations.append(
            FindingCorrelation(
                key=key,
                finding_ids=tuple(str(item.id) for item in ordered),
                asset=asset,
                endpoint=endpoint,
                cwe=cwe,
                highest_severity=highest,
                duplicate_candidate=duplicate_candidate,
            )
        )

    return sorted(
        correlations,
        key=lambda item: (
            not item.duplicate_candidate,
            -_SEVERITY_ORDER.get(item.highest_severity, -1),
            item.key,
        ),
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



def _title_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 3
        and token not in {"the", "and", "for", "with", "from", "this", "that"}
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True)
class FindingSimilarity:
    left_id: str
    right_id: str
    score: float
    same_asset: bool
    same_endpoint: bool
    same_cwe: bool
    title_similarity: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class FindingCluster:
    cluster_id: str
    finding_ids: tuple[str, ...]
    confidence: float
    pair_scores: tuple[float, ...]
    auto_merge: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["finding_ids"] = list(self.finding_ids)
        payload["pair_scores"] = list(self.pair_scores)
        return payload


def score_finding_similarity(left: Any, right: Any) -> FindingSimilarity:
    """Return a conservative duplicate-likelihood score without merging findings."""
    left_asset = _canonical_url(str(left.asset)) or str(left.asset).strip().lower()
    right_asset = _canonical_url(str(right.asset)) or str(right.asset).strip().lower()
    left_endpoint = _canonical_url(getattr(left, "endpoint", None))
    right_endpoint = _canonical_url(getattr(right, "endpoint", None))
    left_cwe = str(left.cwe).strip().upper() if getattr(left, "cwe", None) else None
    right_cwe = str(right.cwe).strip().upper() if getattr(right, "cwe", None) else None

    same_asset = left_asset == right_asset
    same_endpoint = bool(left_endpoint and right_endpoint and left_endpoint == right_endpoint)
    same_cwe = bool(left_cwe and right_cwe and left_cwe == right_cwe)
    title_similarity = _jaccard(
        _title_tokens(getattr(left, "title", None)),
        _title_tokens(getattr(right, "title", None)),
    )

    components = {
        "asset": 0.25 if same_asset else 0.0,
        "endpoint": 0.35 if same_endpoint else 0.0,
        "cwe": 0.25 if same_cwe else 0.0,
        "title": round(title_similarity * 0.15, 4),
    }
    score = round(sum(components.values()), 4)

    # Fail closed: cross-asset records never become duplicate candidates solely
    # because they share a generic title/CWE.
    if not same_asset:
        score = min(score, 0.40)

    reasons = tuple(
        key for key, value in components.items() if value > 0.0
    )
    return FindingSimilarity(
        left_id=str(left.id),
        right_id=str(right.id),
        score=score,
        same_asset=same_asset,
        same_endpoint=same_endpoint,
        same_cwe=same_cwe,
        title_similarity=round(title_similarity, 4),
        reasons=reasons,
    )


def cluster_findings(
    findings: list[Any],
    *,
    threshold: float = 0.75,
) -> tuple[list[FindingCluster], list[FindingSimilarity]]:
    """Cluster likely duplicates non-destructively using high-confidence links."""
    if not 0.50 <= threshold <= 1.0:
        raise ValueError("cluster threshold must be between 0.50 and 1.0")

    ordered = sorted(findings, key=lambda item: str(item.id))
    similarities: list[FindingSimilarity] = []
    adjacency: dict[str, set[str]] = {str(item.id): set() for item in ordered}

    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            similarity = score_finding_similarity(left, right)
            similarities.append(similarity)
            if similarity.score >= threshold:
                adjacency[similarity.left_id].add(similarity.right_id)
                adjacency[similarity.right_id].add(similarity.left_id)

    clusters: list[FindingCluster] = []
    visited: set[str] = set()
    for finding in ordered:
        root = str(finding.id)
        if root in visited:
            continue
        stack = [root]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            stack.extend(sorted(adjacency[current] - visited, reverse=True))

        if len(component) < 2:
            continue

        ids = tuple(sorted(component))
        pair_scores = tuple(
            item.score
            for item in similarities
            if item.left_id in component
            and item.right_id in component
            and item.score >= threshold
        )
        confidence = round(
            sum(pair_scores) / len(pair_scores) if pair_scores else 0.0,
            4,
        )
        clusters.append(
            FindingCluster(
                cluster_id="cluster:" + "|".join(ids),
                finding_ids=ids,
                confidence=confidence,
                pair_scores=pair_scores,
                auto_merge=False,
            )
        )

    return (
        sorted(clusters, key=lambda item: (-item.confidence, item.cluster_id)),
        sorted(similarities, key=lambda item: (-item.score, item.left_id, item.right_id)),
    )


@router.get("/api/campaigns/{campaign_id}/finding-clusters")
def campaign_finding_clusters(campaign_id: str, threshold: float = 0.75):
    from .main import assert_campaign_exists

    campaign = assert_campaign_exists(campaign_id)
    clusters, similarities = cluster_findings(
        campaign.findings,
        threshold=threshold,
    )
    return {
        "campaign_id": campaign.id,
        "threshold": threshold,
        "clusters": [item.to_dict() for item in clusters],
        "similarities": [
            item.to_dict()
            for item in similarities
            if item.score >= threshold
        ],
        "summary": {
            "clusters": len(clusters),
            "clustered_findings": len(
                {finding_id for item in clusters for finding_id in item.finding_ids}
            ),
            "high_confidence_pairs": sum(item.score >= threshold for item in similarities),
        },
        "read_only": True,
        "auto_merge": False,
        "explainable": True,
    }
