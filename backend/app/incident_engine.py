from __future__ import annotations

import hashlib
import json
from typing import Any


_SEVERITY = {"healthy": 0, "degraded": 1, "warning": 1, "critical": 2, "error": 2}


def _state(value: Any) -> str:
    raw = str(value or "healthy").lower()
    if raw in {"critical", "error"}:
        return "critical"
    if raw in {"degraded", "warning"}:
        return "degraded"
    return "healthy"


def _fingerprint(signals: list[dict[str, str]]) -> str:
    canonical = json.dumps(signals, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()[:24]


def build_incident_snapshot(
    watchdog: dict[str, Any],
    slo: dict[str, Any],
    error_budget: dict[str, Any],
) -> dict[str, Any]:
    """Fuse redacted operational signals into one deterministic incident snapshot."""
    sources = {
        "watchdog": _state(watchdog.get("status")),
        "slo": _state(slo.get("state")),
        "error_budget": _state(error_budget.get("state")),
    }
    overall = max(sources.values(), key=lambda item: _SEVERITY[item])

    signals: list[dict[str, str]] = []
    for source, state in sorted(sources.items()):
        if state != "healthy":
            signals.append({"source": source, "state": state})

    incident = None
    if signals:
        incident = {
            "fingerprint": _fingerprint(signals),
            "severity": overall,
            "signals": signals,
            "dedupe_key": "operational:" + _fingerprint(signals),
        }

    return {
        "state": overall,
        "incident": incident,
        "read_only": True,
        "automatic_recovery": False,
        "automatic_retry": False,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
