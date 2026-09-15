from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Thread
from typing import Callable

from .observer_lease import ObserverLease


@dataclass
class LeaseHeartbeat:
    lease: ObserverLease
    owner: str
    generation: int
    ttl_seconds: int
    interval_seconds: float

    def run(self, stop: Event) -> None:
        while not stop.wait(self.interval_seconds):
            if not self.lease.heartbeat(
                self.owner,
                self.generation,
                ttl_seconds=self.ttl_seconds,
            ):
                stop.set()
                return


def with_lease_heartbeat(
    lease: ObserverLease,
    owner: str,
    generation: int,
    ttl_seconds: int,
    callback: Callable[[], object],
):
    """Run a bounded callback while renewing only the current fenced lease."""
    stop = Event()
    heartbeat = LeaseHeartbeat(
        lease=lease,
        owner=owner,
        generation=generation,
        ttl_seconds=ttl_seconds,
        interval_seconds=max(1.0, ttl_seconds / 3),
    )
    thread = Thread(target=heartbeat.run, args=(stop,), daemon=True)
    thread.start()
    try:
        return callback()
    finally:
        stop.set()
        thread.join(timeout=2)
