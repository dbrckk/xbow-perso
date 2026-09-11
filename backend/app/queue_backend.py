from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from .jobqueue import JobQueue


@runtime_checkable
class QueueBackend(Protocol):
    def health(self) -> dict: ...
    def enqueue(self, campaign_id: str, kind: str, payload: dict, max_attempts: int = 2, *, dedupe_key: str | None = None) -> dict: ...
    def get(self, job_id: str) -> dict | None: ...
    def stats(self) -> dict: ...
    def campaign_job_counts(self, campaign_id: str) -> dict[str, int]: ...
    def campaign_job_status_counts(self, campaign_id: str) -> dict[str, int]: ...
    def cancel_queued(self, campaign_id: str) -> int: ...
    def cancel_owned(self, job_id: str, worker_id: str, reason: str = "campaign cancelled") -> dict | None: ...
    def recover_expired_leases(self) -> int: ...
    def claim(self, worker_id: str) -> dict | None: ...
    def heartbeat(self, job_id: str, worker_id: str) -> bool: ...
    def finish(self, job_id: str, worker_id: str, success: bool, error: str | None = None) -> dict | None: ...


def queue_backend_name() -> str:
    value = os.getenv("XBOW_QUEUE_BACKEND", "sqlite").strip().lower()
    aliases = {
        "sqlite3": "sqlite",
        "redis": "redis",
    }
    value = aliases.get(value, value)
    if value not in {"sqlite", "redis"}:
        raise ValueError("XBOW_QUEUE_BACKEND must be sqlite or redis")
    return value


def create_queue() -> QueueBackend:
    backend = queue_backend_name()
    if backend == "sqlite":
        return JobQueue()
    raise RuntimeError(
        "Redis queue backend is selected but not installed; "
        "use XBOW_QUEUE_BACKEND=sqlite until the Redis adapter is configured"
    )
