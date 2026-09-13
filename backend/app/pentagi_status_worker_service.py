from __future__ import annotations

import os
import socket
import time

from .pentagi_status_poller import (
    PentagiPollResult,
    PentagiStatusPollError,
    poll_pentagi_flow_until_terminal,
)
from .pentagi_status_tracker import PentagiStatusTrackingError
from .pentagi_transport import PentagiTransportError
from .pentagi_worker_service import _maintain_lease
from .queue_backend import QueueBackend, create_queue
from .storage_backend import create_storage


class PentagiStatusWorkerError(RuntimeError):
    pass


def _enabled(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _require_runtime() -> None:
    if not _enabled("XBOW_ENABLE_PENTAGI"):
        raise PentagiStatusWorkerError("PentAGI integration is disabled")
    if not _enabled("XBOW_ENABLE_PENTAGI_STATUS_WORKER"):
        raise PentagiStatusWorkerError("PentAGI status worker is disabled")


def _receipt_id(job: dict) -> str:
    if job.get("kind") != "pentagi_status":
        raise PentagiStatusWorkerError("worker received a non-status job")
    payload = job.get("payload")
    if not isinstance(payload, dict):
        raise PentagiStatusWorkerError("PentAGI status job payload is invalid")
    value = payload.get("receipt_artifact_id")
    if not isinstance(value, str) or not value.strip():
        raise PentagiStatusWorkerError("PentAGI receipt artifact id is invalid")
    return value.strip()


def process_one(queue: QueueBackend, store, worker_id: str) -> bool:
    _require_runtime()
    job = queue.claim_kind(worker_id, "pentagi_status")
    if not job:
        return False

    try:
        receipt_id = _receipt_id(job)
        with _maintain_lease(queue, job["id"], worker_id) as lease_lost:
            result: PentagiPollResult = poll_pentagi_flow_until_terminal(
                store,
                job["campaign_id"],
                receipt_id,
            )

        if lease_lost.is_set():
            raise PentagiStatusWorkerError(
                "PentAGI status job lease was lost during polling"
            )

        finished = queue.finish(
            job["id"],
            worker_id,
            not result.timed_out,
            "PentAGI status polling window elapsed" if result.timed_out else None,
        )
        if finished is None:
            raise PentagiStatusWorkerError(
                "PentAGI status job ownership was lost before completion"
            )

        print(
            f"pentagi_status_complete job_id={job['id']} "
            f"flow_id={result.flow_id} status={result.status} "
            f"terminal={str(result.terminal).lower()} "
            f"timed_out={str(result.timed_out).lower()} polls={result.polls}"
        )
        return True
    except (
        PentagiStatusWorkerError,
        PentagiStatusPollError,
        PentagiStatusTrackingError,
        PentagiTransportError,
    ) as exc:
        queue.finish(job["id"], worker_id, False, str(exc))
        return True


def _idle_poll_seconds() -> float:
    raw = (os.getenv("XBOW_PENTAGI_STATUS_WORKER_IDLE_SECONDS") or "1").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            "XBOW_PENTAGI_STATUS_WORKER_IDLE_SECONDS must be numeric"
        ) from exc
    if not 0.2 <= value <= 60.0:
        raise ValueError(
            "XBOW_PENTAGI_STATUS_WORKER_IDLE_SECONDS must be between 0.2 and 60"
        )
    return value


def main() -> None:
    _require_runtime()
    queue = create_queue()
    store = create_storage()
    worker_id = os.getenv(
        "XBOW_PENTAGI_STATUS_WORKER_ID",
        f"pentagi-status:{socket.gethostname()}:{os.getpid()}",
    )
    idle = _idle_poll_seconds()
    while True:
        worked = process_one(queue, store, worker_id)
        if not worked:
            time.sleep(idle)


if __name__ == "__main__":
    main()
