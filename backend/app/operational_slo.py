from __future__ import annotations

import os
from typing import Any


def _threshold(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def build_operational_slo(metrics: dict[str, Any]) -> dict[str, Any]:
    """Classify aggregate service health without inspecting work content."""
    warn_queue = _threshold("XBOW_SLO_WARN_QUEUE_AGE_SECONDS", 120, 1, 86400)
    critical_queue = _threshold("XBOW_SLO_CRITICAL_QUEUE_AGE_SECONDS", 600, 1, 86400)
    warn_failed = _threshold("XBOW_SLO_WARN_FAILED_JOBS", 2, 0, 100000)
    critical_failed = _threshold("XBOW_SLO_CRITICAL_FAILED_JOBS", 10, 0, 100000)
    warn_outbox = _threshold("XBOW_SLO_WARN_OUTBOX_AGE_SECONDS", 60, 1, 86400)
    critical_outbox = _threshold("XBOW_SLO_CRITICAL_OUTBOX_AGE_SECONDS", 300, 1, 86400)

    if warn_queue >= critical_queue:
        raise ValueError("queue SLO warning threshold must be below critical")
    if warn_failed >= critical_failed:
        raise ValueError("failed-job SLO warning threshold must be below critical")
    if warn_outbox >= critical_outbox:
        raise ValueError("outbox SLO warning threshold must be below critical")

    queue_age = int(metrics.get("oldest_queued_age_seconds") or 0)
    failed = int((metrics.get("jobs_by_status") or {}).get("failed") or 0)
    outbox_age = int(metrics.get("oldest_outbox_pending_age_seconds") or 0)

    signals: list[dict[str, Any]] = []

    def classify(name: str, value: int, warning: int, critical: int) -> None:
        if value >= critical:
            signals.append({"name": name, "state": "critical", "value": value})
        elif value >= warning:
            signals.append({"name": name, "state": "degraded", "value": value})

    classify("queue_age_seconds", queue_age, warn_queue, critical_queue)
    classify("failed_jobs", failed, warn_failed, critical_failed)
    classify("outbox_age_seconds", outbox_age, warn_outbox, critical_outbox)

    watchdog = str((metrics.get("worker_watchdog") or {}).get("status") or "ok")
    if watchdog == "error":
        signals.append({"name": "worker_watchdog", "state": "critical"})
    elif watchdog == "warning":
        signals.append({"name": "worker_watchdog", "state": "degraded"})

    state = (
        "critical"
        if any(item["state"] == "critical" for item in signals)
        else "degraded"
        if signals
        else "healthy"
    )
    return {
        "state": state,
        "signals": signals,
        "read_only": True,
        "contains_targets": False,
        "contains_payloads": False,
        "contains_secrets": False,
    }
