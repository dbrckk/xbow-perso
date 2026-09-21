from __future__ import annotations

import math
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from .hackerone_client import HackerOneClient, HackerOneClientError
from .storage import CampaignConflictError


INTELLIGENCE_ID = "current"
_next_attempt_monotonic = 0.0

_SEVERITY_WEIGHT = {
    "critical": 5,
    "high": 3,
    "medium": 2,
    "low": 1,
    "none": 0,
}

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "access_control",
        (
            "idor",
            "insecure direct object",
            "broken access control",
            "improper access control",
            "authorization",
            "authorisation",
            "privilege escalation",
            "bola",
        ),
    ),
    (
        "auth_session",
        (
            "authentication bypass",
            "account takeover",
            "mfa",
            "2fa",
            "oauth",
            "sso",
            "session",
            "password reset",
            "login",
            "credential",
        ),
    ),
    (
        "api_graphql",
        (
            "graphql",
            "rest api",
            "api authorization",
            "api access",
            "mass assignment",
            "api endpoint",
        ),
    ),
    (
        "business_logic",
        (
            "business logic",
            "race condition",
            "double spend",
            "redeem",
            "coupon",
            "discount",
            "payment",
            "refund",
            "vote",
            "workflow",
        ),
    ),
    (
        "xss_client",
        (
            "cross-site scripting",
            "cross site scripting",
            "xss",
            "postmessage",
            "dom",
            "content security policy",
        ),
    ),
    (
        "ssrf_oob",
        (
            "server-side request forgery",
            "server side request forgery",
            "ssrf",
            "xxe",
            "xml external entity",
            "metadata service",
        ),
    ),
    (
        "injection_rce",
        (
            "remote code execution",
            "remote command",
            "command injection",
            "code injection",
            "sql injection",
            "deserialization",
            "template injection",
            "rce",
        ),
    ),
    (
        "cache_proxy",
        (
            "request smuggling",
            "http desync",
            "cache poisoning",
            "web cache",
            "host header",
        ),
    ),
    (
        "cloud_surface",
        (
            "subdomain takeover",
            "dns",
            "bucket",
            "jenkins",
            "exposed admin",
            "cloud",
            "kubernetes",
        ),
    ),
    (
        "file_path",
        (
            "path traversal",
            "directory traversal",
            "file upload",
            "arbitrary file",
            "local file inclusion",
            "lfi",
        ),
    ),
    (
        "information_disclosure",
        (
            "information disclosure",
            "data exposure",
            "sensitive information",
            "secret",
            "source code",
            "internal file",
        ),
    ),
    (
        "ai_llm",
        (
            "prompt injection",
            "llm",
            "large language model",
            "ai agent",
            "model",
        ),
    ),
)

_CAPABILITY_MAP: dict[str, dict[str, Any]] = {
    "access_control": {
        "capability": "authorization-differential",
        "status": "missing",
        "recommended_tooling": ["dual-session request diff", "object-reference mapper"],
        "automatic_execution": False,
    },
    "auth_session": {
        "capability": "auth-state-machine-analysis",
        "status": "missing",
        "recommended_tooling": ["session transition recorder", "OAuth/OIDC/JWT local analyzer"],
        "automatic_execution": False,
    },
    "api_graphql": {
        "capability": "api-schema-intelligence",
        "status": "partial",
        "recommended_tooling": ["OpenAPI mapper", "GraphQL operation/schema mapper"],
        "automatic_execution": False,
    },
    "business_logic": {
        "capability": "state-machine-race-analysis",
        "status": "missing",
        "recommended_tooling": ["workflow modeler", "bounded concurrency harness"],
        "automatic_execution": False,
    },
    "xss_client": {
        "capability": "browser-xss-validation",
        "status": "partial",
        "recommended_tooling": ["Nuclei", "sandboxed browser observation"],
        "automatic_execution": False,
    },
    "ssrf_oob": {
        "capability": "ssrf-oob-validation",
        "status": "missing",
        "recommended_tooling": ["URL-sink mapper", "explicitly configured OAST callback"],
        "automatic_execution": False,
    },
    "injection_rce": {
        "capability": "injection-validation",
        "status": "partial",
        "recommended_tooling": ["Nuclei", "context-aware non-destructive confirmation"],
        "automatic_execution": False,
    },
    "cache_proxy": {
        "capability": "proxy-cache-differential",
        "status": "missing",
        "recommended_tooling": ["cache-key mapper", "manual-only HTTP desync harness"],
        "automatic_execution": False,
    },
    "cloud_surface": {
        "capability": "passive-asset-expansion",
        "status": "missing",
        "recommended_tooling": ["certificate-transparency mapper", "passive DNS/subdomain mapper"],
        "automatic_execution": False,
    },
    "file_path": {
        "capability": "file-boundary-analysis",
        "status": "partial",
        "recommended_tooling": ["Nuclei", "upload/path semantic mapper"],
        "automatic_execution": False,
    },
    "information_disclosure": {
        "capability": "sensitive-response-analysis",
        "status": "partial",
        "recommended_tooling": ["response diff", "public JavaScript/source-map inspection"],
        "automatic_execution": False,
    },
    "ai_llm": {
        "capability": "ai-application-analysis",
        "status": "missing",
        "recommended_tooling": ["prompt-boundary mapper", "tool/data access observation"],
        "automatic_execution": False,
    },
    "other": {
        "capability": "general-analysis",
        "status": "partial",
        "recommended_tooling": ["Nuclei", "read-only recon", "browser observation"],
        "automatic_execution": False,
    },
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    return text[:limit]


def _amount(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number) or number < 0:
        return 0.0
    return min(number, 100_000_000.0)


def _bounded_int(value: Any, *, minimum: int = 0, maximum: int = 10_000_000) -> int:
    if isinstance(value, bool):
        return minimum
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return minimum
    return max(minimum, min(number, maximum))


def _relationship_attributes(resource: dict[str, Any], name: str) -> dict[str, Any]:
    relationships = resource.get("relationships")
    if not isinstance(relationships, dict):
        return {}
    rel = relationships.get(name)
    if not isinstance(rel, dict):
        return {}
    data = rel.get("data")
    if not isinstance(data, dict):
        return {}
    attributes = data.get("attributes")
    return attributes if isinstance(attributes, dict) else {}


def normalize_hacktivity_item(resource: Any) -> dict[str, Any] | None:
    if not isinstance(resource, dict):
        return None
    attributes = resource.get("attributes")
    if not isinstance(attributes, dict) or attributes.get("disclosed") is not True:
        return None

    report_id = _bounded_text(resource.get("id"), 64)
    if not report_id:
        return None

    severity = _bounded_text(attributes.get("severity_rating"), 32).lower()
    if severity not in _SEVERITY_WEIGHT:
        severity = "none"

    program = _relationship_attributes(resource, "program")
    generated = _relationship_attributes(resource, "report_generated_content")
    currency = _bounded_text(program.get("currency"), 12).upper()
    if len(currency) > 3:
        currency = ""

    return {
        "id": report_id,
        "title": _bounded_text(attributes.get("title"), 300),
        "url": _bounded_text(attributes.get("url"), 1024),
        "disclosed_at": _bounded_text(attributes.get("disclosed_at"), 64),
        "submitted_at": _bounded_text(attributes.get("submitted_at"), 64),
        "cwe": _bounded_text(attributes.get("cwe"), 160),
        "severity": severity,
        "votes": _bounded_int(attributes.get("votes")),
        "award_amount": _amount(attributes.get("total_awarded_amount")),
        "currency": currency,
        "program_handle": _bounded_text(program.get("handle"), 128),
        "program_name": _bounded_text(program.get("name"), 200),
        "summary": _bounded_text(generated.get("hacktivity_summary"), 800),
    }


def classify_report(report: dict[str, Any]) -> str:
    haystack = " ".join(
        (
            str(report.get("title") or ""),
            str(report.get("cwe") or ""),
            str(report.get("summary") or ""),
        )
    ).lower()
    for category, keywords in _CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "other"


def _max_pages() -> int:
    raw = (os.getenv("XBOW_HACKERONE_INTEL_MAX_PAGES") or "2").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("XBOW_HACKERONE_INTEL_MAX_PAGES must be an integer") from exc
    if not 1 <= value <= 5:
        raise ValueError("XBOW_HACKERONE_INTEL_MAX_PAGES must be between 1 and 5")
    return value


def intelligence_poll_seconds() -> int:
    raw = (os.getenv("XBOW_HACKERONE_INTEL_POLL_SECONDS") or "21600").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("XBOW_HACKERONE_INTEL_POLL_SECONDS must be an integer") from exc
    if not 900 <= value <= 604800:
        raise ValueError(
            "XBOW_HACKERONE_INTEL_POLL_SECONDS must be between 900 and 604800"
        )
    return value


def _enabled() -> bool:
    raw = (os.getenv("XBOW_ENABLE_HACKERONE_INTELLIGENCE") or "true").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError("XBOW_ENABLE_HACKERONE_INTELLIGENCE must be a boolean")


def fetch_disclosed_hacktivity(
    *,
    client: HackerOneClient | None = None,
) -> list[dict[str, Any]]:
    api = client or HackerOneClient()
    pages = _max_pages()
    common = {"queryString": "disclosed:true"}

    high_value = api.get_all_pages(
        "hackers/hacktivity",
        {**common, "sort": "-total_awarded_amount"},
        max_pages=pages,
        page_size=100,
    )
    recent = api.get_all_pages(
        "hackers/hacktivity",
        {**common, "sort": "-disclosed_at"},
        max_pages=pages,
        page_size=100,
    )

    deduped: dict[str, dict[str, Any]] = {}
    for resource in [*high_value, *recent]:
        item = normalize_hacktivity_item(resource)
        if item is not None:
            deduped[item["id"]] = item
    return list(deduped.values())[:500]


def _category_statistics(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for report in reports:
        category = classify_report(report)
        item = stats.setdefault(
            category,
            {
                "category": category,
                "report_count": 0,
                "high_critical_count": 0,
                "usd_awarded_total": 0.0,
                "usd_awarded_max": 0.0,
                "severity_points": 0,
                "examples": [],
            },
        )
        item["report_count"] += 1
        severity = str(report.get("severity") or "none")
        item["severity_points"] += _SEVERITY_WEIGHT.get(severity, 0)
        if severity in {"critical", "high"}:
            item["high_critical_count"] += 1
        if report.get("currency") == "USD":
            amount = float(report.get("award_amount") or 0)
            item["usd_awarded_total"] += amount
            item["usd_awarded_max"] = max(item["usd_awarded_max"], amount)
        if len(item["examples"]) < 5:
            item["examples"].append(
                {
                    "id": report.get("id"),
                    "title": report.get("title"),
                    "program_handle": report.get("program_handle"),
                    "severity": severity,
                    "award_amount": report.get("award_amount"),
                    "currency": report.get("currency"),
                    "url": report.get("url"),
                }
            )

    for item in stats.values():
        evidence = (
            item["report_count"]
            + (2 * item["high_critical_count"])
            + min(20.0, math.log2(1.0 + item["usd_awarded_total"]))
        )
        item["evidence_score"] = round(evidence, 3)
        item["usd_awarded_total"] = round(item["usd_awarded_total"], 2)
        item["usd_awarded_max"] = round(item["usd_awarded_max"], 2)

    return sorted(
        stats.values(),
        key=lambda item: (
            -float(item["evidence_score"]),
            -int(item["high_critical_count"]),
            str(item["category"]),
        ),
    )


def _program_signals(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    categories: dict[str, Counter[str]] = defaultdict(Counter)
    for report in reports:
        handle = str(report.get("program_handle") or "").strip()
        if not handle:
            continue
        entry = grouped.setdefault(
            handle,
            {
                "program_handle": handle,
                "program_name": report.get("program_name") or handle,
                "disclosed_report_count": 0,
                "high_critical_count": 0,
                "usd_awarded_total": 0.0,
                "usd_awarded_max": 0.0,
                "historical_only": True,
            },
        )
        entry["disclosed_report_count"] += 1
        if report.get("severity") in {"critical", "high"}:
            entry["high_critical_count"] += 1
        if report.get("currency") == "USD":
            amount = float(report.get("award_amount") or 0)
            entry["usd_awarded_total"] += amount
            entry["usd_awarded_max"] = max(entry["usd_awarded_max"], amount)
        categories[handle][classify_report(report)] += 1

    for handle, entry in grouped.items():
        entry["usd_awarded_total"] = round(entry["usd_awarded_total"], 2)
        entry["usd_awarded_max"] = round(entry["usd_awarded_max"], 2)
        entry["top_categories"] = [
            category for category, _ in categories[handle].most_common(4)
        ]
        entry["historical_value_score"] = round(
            (
                entry["disclosed_report_count"]
                + (2 * entry["high_critical_count"])
                + min(20.0, math.log2(1.0 + entry["usd_awarded_total"]))
            ),
            3,
        )
    return grouped


def _capability_gaps(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for category in categories:
        name = str(category["category"])
        mapping = dict(_CAPABILITY_MAP.get(name, _CAPABILITY_MAP["other"]))
        result.append(
            {
                "category": name,
                "evidence_score": category["evidence_score"],
                "report_count": category["report_count"],
                "high_critical_count": category["high_critical_count"],
                "usd_awarded_max": category["usd_awarded_max"],
                **mapping,
            }
        )
    return result


def build_hackerone_intelligence(reports: list[dict[str, Any]]) -> dict[str, Any]:
    categories = _category_statistics(reports)
    programs = _program_signals(reports)

    high_value_reports = sorted(
        reports,
        key=lambda item: (
            item.get("currency") != "USD",
            -float(item.get("award_amount") or 0),
            -_SEVERITY_WEIGHT.get(str(item.get("severity") or "none"), 0),
            -int(item.get("votes") or 0),
        ),
    )[:60]
    recent_reports = sorted(
        reports,
        key=lambda item: str(item.get("disclosed_at") or ""),
        reverse=True,
    )[:60]

    now = _utcnow()
    return {
        "id": INTELLIGENCE_ID,
        "provider": "hackerone",
        "source": "public_disclosed_hacktivity",
        "reports": reports,
        "report_count": len(reports),
        "categories": categories,
        "program_signals": programs,
        "capability_gaps": _capability_gaps(categories),
        "high_value_reports": high_value_reports,
        "recent_reports": recent_reports,
        "checked_at": now,
        "updated_at": now,
        "limitations": [
            "Disclosed Hacktivity is a public subset and is not representative of all valid reports.",
            "Historical disclosed awards are not current bounty-table promises.",
            "USD award signals are compared only when the report currency is USD.",
            "This intelligence never authorizes a target or expands program scope.",
        ],
        "contains_secrets": False,
        "automatic_tool_enablement": False,
    }


def refresh_hackerone_intelligence(
    store,
    *,
    client: HackerOneClient | None = None,
) -> dict[str, Any]:
    reports = fetch_disclosed_hacktivity(client=client)
    state = build_hackerone_intelligence(reports)

    for _ in range(3):
        record = store.get_hackerone_intelligence_state_record(INTELLIGENCE_ID)
        expected_version = 0 if record is None else record[1]
        try:
            store.save_hackerone_intelligence_state(
                state,
                expected_version=expected_version,
            )
            return state
        except CampaignConflictError:
            continue

    latest = store.get_hackerone_intelligence_state(INTELLIGENCE_ID)
    if latest is None:
        raise CampaignConflictError("HackerOne intelligence update conflicted")
    return latest


def maybe_refresh_hackerone_intelligence(store) -> dict[str, Any]:
    global _next_attempt_monotonic

    if not _enabled():
        return {"status": "disabled"}

    now = time.monotonic()
    if now < _next_attempt_monotonic:
        return {"status": "not_due"}

    _next_attempt_monotonic = now + intelligence_poll_seconds()
    try:
        state = refresh_hackerone_intelligence(store)
    except HackerOneClientError:
        return {"status": "unavailable"}
    except CampaignConflictError:
        return {"status": "conflict"}

    return {
        "status": "refreshed",
        "report_count": state.get("report_count", 0),
        "checked_at": state.get("checked_at"),
    }
