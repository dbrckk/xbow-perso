from __future__ import annotations

import os
from typing import Any, Callable

from .observer_lease import ObserverLease


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
    observe_once: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Perform one leader-gated observation pass; external scheduler controls timing."""
    config = scheduler_config()
    if not lease.acquire(owner, ttl_seconds=config["lease_ttl_seconds"]):
        return {"ran": False, "reason": "not_leader"}
    try:
        result = observe_once()
        return {"ran": True, "result": result}
    finally:
        lease.release(owner)
