from __future__ import annotations

from threading import RLock

from .observer_resilience import ObserverHealth


class ObserverRuntime:
    """Process-local owner of scheduler health with synchronized snapshots."""

    def __init__(self):
        self._lock = RLock()
        self._health = ObserverHealth()

    @property
    def health(self) -> ObserverHealth:
        return self._health

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._health.snapshot())


_runtime = ObserverRuntime()


def observer_runtime() -> ObserverRuntime:
    return _runtime
