from __future__ import annotations

from typing import Any


_GAP_RUNTIME_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "access_control": ("browser",),
    "auth_session": ("browser",),
    "api_graphql": ("recon",),
    "business_logic": ("browser",),
    "xss_client": ("browser", "scanner"),
    "ssrf_oob": ("recon",),
    "injection_rce": ("scanner",),
    "cache_proxy": ("recon",),
    "cloud_surface": ("recon",),
    "file_path": ("browser", "scanner"),
    "information_disclosure": ("recon",),
    "ai_llm": ("browser",),
    "other": ("recon",),
}

_STATUS_FACTOR = {"missing": 1.0, "partial": 0.55, "available": 0.0}


def runtime_capability_snapshot(
    *,
    scanner: dict[str, Any],
    recon: dict[str, Any],
    browser_available: bool = True,
) -> dict[str, Any]:
    """Normalize redacted runtime readiness used only for advisory gap ranking."""
    return {
        "scanner": bool(scanner.get("dispatch_ready")),
        "recon": bool(recon.get("dispatch_ready")),
        "browser": bool(browser_available),
        "scanner_mode": str(scanner.get("mode") or "unknown"),
        "recon_mode": str(recon.get("mode") or "unknown"),
        "contains_secrets": False,
    }


def rank_runtime_capability_gaps(
    gaps: list[dict[str, Any]],
    runtime: dict[str, Any],
) -> list[dict[str, Any]]:
    """Rank historical capability gaps against current runtime readiness.

    This is advisory only. Readiness never enables a tool, expands scope, creates
    requests, or changes a campaign action.
    """
    ranked: list[dict[str, Any]] = []
    for gap in gaps:
        category = str(gap.get("category") or "other")
        required = _GAP_RUNTIME_REQUIREMENTS.get(category, ("recon",))
        ready = [name for name in required if bool(runtime.get(name))]
        unavailable = [name for name in required if not bool(runtime.get(name))]
        declared_status = str(gap.get("status") or "missing")
        evidence = max(0.0, float(gap.get("evidence_score") or 0.0))
        high_critical = max(0, int(gap.get("high_critical_count") or 0))
        gap_factor = _STATUS_FACTOR.get(declared_status, 1.0)

        # Prioritize strong public evidence where declared analysis coverage is
        # weak. Runtime readiness is surfaced separately rather than interpreted
        # as permission to execute anything.
        priority = round((evidence + (2.0 * high_critical)) * gap_factor, 3)
        ranked.append(
            {
                **gap,
                "runtime_requirements": list(required),
                "runtime_ready": ready,
                "runtime_unavailable": unavailable,
                "runtime_coverage": (
                    "ready" if not unavailable else ("partial" if ready else "unavailable")
                ),
                "investment_priority": priority,
                "advisory_only": True,
                "automatic_tool_enablement": False,
                "scope_expansion": False,
            }
        )

    ranked.sort(
        key=lambda item: (
            -float(item["investment_priority"]),
            len(item["runtime_unavailable"]),
            str(item["category"]),
        )
    )
    return ranked
