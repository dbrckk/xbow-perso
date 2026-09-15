from __future__ import annotations

import os
from typing import Any, Callable

from .observer_lease import ObserverLease
from .observer_resilience import ObserverHealth


def scheduler_config() -> dict[str, int]:
    interval = int(os.getenv("XBOW_INCIDENT_OBSERVER_INTERVAL_SECONDS", "30"))
    ttl = int(os.getenv("XBOW_INCIDENT_OBSERVER_LEASE_TTL_SECONDS", "90"))
    if not 10 <= interval <= 3600:
        raise ValueError("observer interval must be between 10 and 3600 seconds")
    if not max(10, interval * 2) <= ttl <= 3600:
        raise ValueError("observer lease TTL must be at least 2x interval and <= 3600")
    return {"interval_seconds": interval, "lease_ttl_seconds": ttl}


def run_scheduled_observation(
    lease: ObserverLease,
    owner: str,
    observe_once: Callable[[str, int], dict[str, Any]],
    health: ObserverHealth | None = None,
) -> dict[str, Any]:
    """Perform one leader-gated observation pass; external scheduler controls timing."""
    config = scheduler_config()
    health = health or ObserverHealth()
    if health.circuit_open():
        return {"ran": False, "reason": "circuit_open", "health": health.snapshot()}
    generation = lease.acquire(owner, ttl_seconds=config["lease_ttl_seconds"])
    if generation is None:
        return {"ran": False, "reason": "not_leader", "health": health.snapshot()}
    health.note_generation(generation)
    try:
        if not lease.is_current(owner, generation):
            return {"ran": False, "reason": "leadership_lost", "generation": generation}
        try:
            result = observe_once(owner, generation)
        except Exception:
            health.failure()
            raise
        if not lease.is_current(owner, generation):
            return {"ran": False, "reason": "leadership_lost_after_observation", "generation": generation}
        health.success()
        return {
            "ran": True,
            "result": result,
            "generation": generation,
            "health": health.snapshot(),
        }
    finally:
        lease.release(owner, generation)
