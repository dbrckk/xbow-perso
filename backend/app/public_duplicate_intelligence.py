from __future__ import annotations

import re
from typing import Any


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,}", re.IGNORECASE)
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "into", "via", "using",
    "http", "https", "www", "com", "bug", "issue", "vulnerability",
}
MAX_PUBLIC_REPORTS_COMPARED = 500
MAX_MATCHES = 10
MAX_LOCAL_TEXT = 1200


def _bounded(value: Any, limit: int = MAX_LOCAL_TEXT) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def _tokens(*values: Any) -> set[str]:
    joined = " ".join(_bounded(value) for value in values).lower()
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
    """Compare a finding with the cached public disclosed Hacktivity subset.

    The result is advisory similarity only. It never predicts HackerOne's
    duplicate decision, blocks reporting, expands scope, or performs network I/O.
    """
    if not 1 <= limit <= MAX_MATCHES:
        raise ValueError(f"duplicate-risk limit must be between 1 and {MAX_MATCHES}")

    finding_tokens = _tokens(
        getattr(finding, "title", ""),
        getattr(finding, "summary", ""),
        getattr(finding, "cwe", ""),
    )
    expected_handle = _bounded(program_handle, 128).lower()
    matches: list[dict[str, Any]] = []

    for report in reports[:MAX_PUBLIC_REPORTS_COMPARED]:
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

        report_handle = _bounded(report.get("program_handle"), 128).lower()
        same_program = bool(expected_handle and report_handle == expected_handle)
        similarity_signal = min(1.0, base_similarity + (0.10 if same_program else 0.0))
        matches.append(
            {
                "report_id": _bounded(report.get("id"), 64),
                "title": _bounded(report.get("title"), 300),
                "url": _bounded(report.get("url"), 1024),
                "program_handle": report_handle,
                "same_program": same_program,
                "similarity": round(base_similarity, 3),
                "similarity_signal": round(similarity_signal, 3),
                "severity": _bounded(report.get("severity"), 32),
            }
        )

    matches.sort(
        key=lambda item: (
            -float(item["similarity_signal"]),
            not bool(item["same_program"]),
            str(item["report_id"]),
        )
    )
    top = matches[:limit]
    max_signal = float(top[0]["similarity_signal"]) if top else 0.0

    if max_signal >= 0.65:
        band = "high_public_similarity"
    elif max_signal >= 0.35:
        band = "medium_public_similarity"
    elif max_signal > 0:
        band = "low_public_similarity"
    else:
        band = "no_public_similarity"

    return {
        "similarity_signal": round(max_signal, 3),
        "novelty_signal": round(1.0 - max_signal, 3),
        "similarity_band": band,
        "matches": top,
        "reports_compared": min(len(reports), MAX_PUBLIC_REPORTS_COMPARED),
        "public_subset_only": True,
        "does_not_predict_platform_duplicate_decision": True,
        "advisory_only": True,
        "automatic_report_block": False,
        "network_requests_sent": 0,
    }
