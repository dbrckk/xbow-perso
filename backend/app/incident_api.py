from __future__ import annotations

from typing import Any

from .incident_lifecycle import acknowledge_incident, incident_reliability_stats
from .domain_incident_lifecycle import active_incidents_by_domain
from .incident_store import IncidentStore, IncidentStoreConflict


class IncidentApiConflict(RuntimeError):
    pass


def read_incident_status(store: IncidentStore) -> dict[str, Any]:
    history, version = store.read()
    active_by_domain = active_incidents_by_domain(history)
    active = [item for item in active_by_domain.values() if item is not None]
    return {
        "version": version,
        "active": active,
        "active_by_domain": active_by_domain,
        "history": history,
        "reliability": incident_reliability_stats(history),
        "read_only": True,
    }


def acknowledge_incident_versioned(
    store: IncidentStore,
    fingerprint: str,
    *,
    expected_version: int,
) -> dict[str, Any]:
    history, current_version = store.read()
    if current_version != expected_version:
        raise IncidentApiConflict("incident state changed concurrently")

    updated = acknowledge_incident(history, fingerprint)
    if updated == history:
        return {
            "changed": False,
            "version": current_version,
            "reason": "incident_not_open",
        }
    try:
        new_version = store.write(updated, expected_version=current_version)
    except IncidentStoreConflict as exc:
        raise IncidentApiConflict("incident state changed concurrently") from exc
    return {
        "changed": True,
        "version": new_version,
        "fingerprint": fingerprint,
    }
