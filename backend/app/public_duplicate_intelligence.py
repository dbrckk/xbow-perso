from __future__ import annotations

import re
from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,}", re.IGNORECASE)
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "into", "via", "using",
    "http", "https", "www", "com", "bug", "issue", "vulnerability",
}


def _tokens(*values: Any) -> set[str]:
    joined = " ".join(str(value or "") for value in values).lower()
    return {
        token
        for token in _TOKEN_RE.findall(joined)
        if token not in _STOP and not token.isdigit()
    }


def _similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def rank_public_duplicate_risk(
    finding: Any,
    reports: list[dict[str, Any]],
    *,
    program_handle: str | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Compare a local finding with already-public disclosed reports.

    Similarity is advisory only. Public Hacktivity is incomplete and a similar
    title/summary does not prove that a report would be a duplicate.
    """
    if not 1 <= limit <= 10:
        raise ValueError("duplicate-risk limit must be between 1 and 10")

    finding_tokens = _tokens(
        getattr(finding, "title", ""),
        getattr(finding, "summary", ""),
        getattr(finding, "cwe", ""),
    )
    expected_handle = str(program_handle or "").strip().lower()
    matches: list[dict[str, Any]] = []

    for report in reports[:1000]:
        if not isinstance(report, dict):
            continue
        report_tokens = _tokens(
            report.get("title"),
            report.get("summary"),
            report.get("cwe"),
        )
        base_similarity = _similarity(finding_tokens, report_tokens)
        if base_similarity <= 0:
            continue
        report_handle = str(report.get("program_handle") or "").strip().lower()
        same_program = bool(expected_handle and report_handle == expected_handle)
        risk = min(1.0, base_similarity + (0.10 if same_program else 0.0))
        matches.append({
            "report_id": str(report.get("id") or ""),
            "title": str(report.get("title") or "")[:300],
            "url": str(report.get("url") or "")[:1024],
            "program_handle": report_handle,
            "same_program": same_program,
            "similarity": round(base_similarity, 3),
            "risk_score": round(risk, 3),
            "severity": str(report.get("severity") or ""),
            "award_amount": float(report.get("award_amount") or 0.0),
            "currency": str(report.get("currency") or ""),
        })

    matches.sort(
        key=lambda item: (
            -float(item["risk_score"]),
            not bool(item["same_program"]),
            -float(item["award_amount"]),
            str(item["report_id"]),
        )
    )
    top = matches[:limit]
    max_risk = float(top[0]["risk_score"]) if top else 0.0
    if max_risk >= 0.65:
        band = "high_public_similarity"
    elif max_risk >= 0.35:
        band = "medium_public_similarity"
    elif max_risk > 0:
        band = "low_public_similarity"
    else:
        band = "no_public_similarity"

    return {
        "risk_score": round(max_risk, 3),
        "novelty_score": round(1.0 - max_risk, 3),
        "risk_band": band,
        "matches": top,
        "public_subset_only": True,
        "does_not_predict_platform_duplicate_decision": True,
        "advisory_only": True,
        "automatic_report_block": False,
    }
