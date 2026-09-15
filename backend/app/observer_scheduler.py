from __future__ import annotations

import os
import time
from typing import Any, Callable

from .observer_lease import ObserverLease
from .observer_resilience import ObserverHealth
from .observer_heartbeat import with_lease_heartbeat
from .observer_runtime import observer_runtime


def scheduler_config() -> dict[str, int]:
    interval = int(os.getenv("XBOW_INCIDENT_OBSERVER_INTERVAL_SECONDS", "30"))
    ttl = int(os.getenv("XBOW_INCIDENT_OBSERVER_LEASE_TTL_SECONDS", "90"))
    if not 10 <= interval <= 3600:
        raise ValueError("observer interval must be between 10 and 3600 seconds")
    if not max(10, interval * 2) <= ttl <= 3600:
        raise ValueError("observer lease TTL must be at least 2x interval and <= 3600")
    deadline = int(os.getenv("XBOW_INCIDENT_OBSERVER_DEADLINE_SECONDS", "60"))
    if not 5 <= deadline < ttl:
        raise ValueError("observer deadline must be >= 5 seconds and below lease TTL")
    return {
        "interval_seconds": interval,
        "lease_ttl_seconds": ttl,
        "deadline_seconds": deadline,
    }


def run_scheduled_observation(
    lease: ObserverLease,
    owner: str,
    observe_once: Callable[[str, int], dict[str, Any]],
    health: ObserverHealth | None = None,
) -> dict[str, Any]:
    """Perform one leader-gated observation pass; external scheduler controls timing."""
    config = scheduler_config()
    health = health or observer_runtime().health
    if health.circuit_open():
        return {"ran": False, "reason": "circuit_open", "health": health.snapshot()}
    generation = lease.acquire(owner, ttl_seconds=config["lease_ttl_seconds"])
    if generation is None:
        return {"ran": False, "reason": "not_leader", "health": health.snapshot()}
    health.note_generation(generation)
    try:
        if not lease.is_current(owner, generation):
            health.note_leadership_lost()
            return {"ran": False, "reason": "leadership_lost", "generation": generation, "health": health.snapshot()}
        started = time.monotonic()
        try:
            result = with_lease_heartbeat(
                lease,
                owner,
                generation,
                config["lease_ttl_seconds"],
                lambda: observe_once(owner, generation),
            )
        except Exception:
            health.failure()
            raise
        elapsed = time.monotonic() - started
        health.note_cycle_duration(elapsed)
        if elapsed > config["deadline_seconds"]:
            health.note_deadline_exceeded()
            health.failure()
            return {
                "ran": False,
                "reason": "deadline_exceeded",
                "generation": generation,
                "elapsed_seconds": elapsed,
                "health": health.snapshot(),
            }
        if not lease.is_current(owner, generation):
            health.note_leadership_lost()
            return {"ran": False, "reason": "leadership_lost_after_observation", "generation": generation, "health": health.snapshot()}
        health.success()
        return {
            "ran": True,
            "result": result,
            "generation": generation,
            "health": health.snapshot(),
        }
    finally:
        lease.release(owner, generation)
