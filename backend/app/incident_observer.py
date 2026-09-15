from __future__ import annotations

from typing import Any, Callable

from .error_budget import build_error_budget_status
from .incident_engine import build_incident_snapshot
from .incident_lifecycle import apply_incident_snapshot
from .incident_store import IncidentStore, IncidentStoreConflict
from .operational_slo import build_operational_slo


def observe_incidents(
    store: IncidentStore,
    metrics: dict[str, Any],
    telemetry: dict[str, Any],
    *,
    max_conflict_retries: int = 3,
) -> dict[str, Any]:
    """Evaluate and persist operational incident state without execution side effects."""
    slo = build_operational_slo(metrics)
    budget = build_error_budget_status(telemetry)
    watchdog = metrics.get("worker_watchdog") or {"status": "error"}
    snapshot = build_incident_snapshot(watchdog, slo, budget)

    for attempt in range(max_conflict_retries):
        history, version = store.read()
        updated = apply_incident_snapshot(history, snapshot)
        if updated == history:
            return {
                "changed": False,
                "version": version,
                "state": snapshot["state"],
                "conflict_retries": attempt,
            }
        try:
            new_version = store.write(updated, expected_version=version)
            return {
                "changed": True,
                "version": new_version,
                "state": snapshot["state"],
                "conflict_retries": attempt,
            }
        except IncidentStoreConflict:
            continue

    raise IncidentStoreConflict("incident observer conflict retry budget exhausted")


def run_incident_observation(
    store: IncidentStore,
    metrics_provider: Callable[[], dict[str, Any]],
    telemetry_provider: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Single scheduler-friendly observation pass."""
    return observe_incidents(store, metrics_provider(), telemetry_provider())
