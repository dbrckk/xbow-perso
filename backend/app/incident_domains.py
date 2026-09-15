from __future__ import annotations

import hashlib
import json
from typing import Any


_SEVERITY = {"healthy": 0, "degraded": 1, "critical": 2}


def _state(value: Any) -> str:
    raw = str(value or "healthy").lower()
    if raw in {"critical", "error"}:
        return "critical"
    if raw in {"degraded", "warning"}:
        return "degraded"
    return "healthy"


def _fingerprint(domain: str, signals: list[dict[str, str]]) -> str:
    raw = json.dumps(
        {"domain": domain, "signals": signals},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def build_domain_incidents(
    watchdog: dict[str, Any],
    slo: dict[str, Any],
    error_budget: dict[str, Any],
    observer: dict[str, Any],
) -> dict[str, Any]:
    """Create independent redacted incident snapshots per operational domain."""
    domain_sources = {
        "workload": {
            "slo": _state(slo.get("state")),
            "error_budget": _state(error_budget.get("state")),
        },
        "control_plane": {
            "watchdog": _state(watchdog.get("status")),
        },
        "observability": {
            "observer": _state(observer.get("state")),
        },
    }

    incidents: dict[str, dict[str, Any] | None] = {}
    overall = "healthy"
    for domain, sources in domain_sources.items():
        signals = [
            {"source": source, "state": state}
            for source, state in sorted(sources.items())
            if state != "healthy"
        ]
        if not signals:
            incidents[domain] = None
            continue
        severity = max((item["state"] for item in signals), key=lambda s: _SEVERITY[s])
        if _SEVERITY[severity] > _SEVERITY[overall]:
            overall = severity
        fingerprint = _fingerprint(domain, signals)
        incidents[domain] = {
            "domain": domain,
            "severity": severity,
            "fingerprint": fingerprint,
            "dedupe_key": f"operational:{domain}:{fingerprint}",
            "signals": signals,
        }

    return {
        "state": overall,
        "incidents": incidents,
        "read_only": True,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
