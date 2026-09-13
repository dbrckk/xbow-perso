from app.jobqueue import JobQueue
from app.pentagi_status_poller import PentagiPollResult
from app.pentagi_status_worker_service import (
    PentagiStatusWorkerError,
    _require_runtime,
    process_one,
)


def _enable(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_STATUS_WORKER", "true")


def test_status_worker_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_PENTAGI", raising=False)
    monkeypatch.delenv("XBOW_ENABLE_PENTAGI_STATUS_WORKER", raising=False)
    try:
        _require_runtime()
    except PentagiStatusWorkerError:
        pass
    else:
        raise AssertionError("status worker must be explicitly enabled")


def test_status_jobs_are_invisible_to_generic_workers(tmp_path):
    queue = JobQueue(str(tmp_path / "q.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "pentagi_status",
        {"receipt_artifact_id": "receipt-1"},
        max_attempts=1,
        dedupe_key="pentagi:status:1",
    )

    assert queue.claim("generic-worker") is None
    claimed = queue.claim_kind("status-worker", "pentagi_status")
    assert claimed is not None
    assert claimed["id"] == job["id"]


def test_status_worker_completes_terminal_tracking_job(tmp_path, monkeypatch):
    _enable(monkeypatch)
    queue = JobQueue(str(tmp_path / "q.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "pentagi_status",
        {"receipt_artifact_id": "receipt-1"},
        max_attempts=1,
        dedupe_key="pentagi:status:1",
    )

    monkeypatch.setattr(
        "app.pentagi_status_worker_service.poll_pentagi_flow_until_terminal",
        lambda *args, **kwargs: PentagiPollResult(
            flow_id="flow-42",
            status="finished",
            polls=3,
            terminal=True,
            timed_out=False,
        ),
    )

    assert process_one(queue, object(), "status-worker") is True
    assert queue.get(job["id"])["status"] == "completed"


def test_status_worker_completes_bounded_timeout_job(tmp_path, monkeypatch):
    _enable(monkeypatch)
    queue = JobQueue(str(tmp_path / "q.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "pentagi_status",
        {"receipt_artifact_id": "receipt-1"},
        max_attempts=1,
        dedupe_key="pentagi:status:1",
    )

    monkeypatch.setattr(
        "app.pentagi_status_worker_service.poll_pentagi_flow_until_terminal",
        lambda *args, **kwargs: PentagiPollResult(
            flow_id="flow-42",
            status="running",
            polls=5,
            terminal=False,
            timed_out=True,
        ),
    )

    assert process_one(queue, object(), "status-worker") is True
    assert queue.get(job["id"])["status"] == "completed"
