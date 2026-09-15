import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.jobqueue import JobQueue


def _queue_audit_module():
    try:
        return importlib.import_module("app.queue_audit")
    except ModuleNotFoundError as exc:
        pytest.fail(f"queue audit contract not implemented: {exc}")


def _event(module, *, seq, from_status, to_status, previous_hash, at):
    return module.build_transition_event(
        job_id="job-1",
        campaign_id="campaign-1",
        kind="report",
        seq=seq,
        from_status=from_status,
        to_status=to_status,
        actor="worker-a" if from_status is not None else "queue",
        reason="job transitioned",
        at=at,
        previous_hash=previous_hash,
    )


def test_transition_chain_accepts_valid_lifecycle():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    second = _event(
        audit,
        seq=2,
        from_status="queued",
        to_status="running",
        previous_hash=first["event_hash"],
        at="t2",
    )
    third = _event(
        audit,
        seq=3,
        from_status="running",
        to_status="completed",
        previous_hash=second["event_hash"],
        at="t3",
    )

    result = audit.verify_transition_events([first, second, third])

    assert result == {
        "valid": True,
        "reason": None,
        "checked": 3,
        "final_status": "completed",
        "head_hash": third["event_hash"],
    }


def test_transition_chain_rejects_sequence_gap():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    forged = dict(first, seq=3)

    result = audit.verify_transition_events([first, forged])

    assert result["valid"] is False
    assert result["reason"] == "transition sequence gap"
    assert result["checked"] == 1


def test_transition_chain_rejects_status_discontinuity():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    forged = _event(
        audit,
        seq=2,
        from_status="running",
        to_status="completed",
        previous_hash=first["event_hash"],
        at="t2",
    )

    result = audit.verify_transition_events([first, forged])

    assert result["valid"] is False
    assert result["reason"] == "transition status discontinuity"
    assert result["checked"] == 1


def test_transition_chain_rejects_hash_discontinuity():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    second = _event(
        audit,
        seq=2,
        from_status="queued",
        to_status="running",
        previous_hash="0" * 64,
        at="t2",
    )

    result = audit.verify_transition_events([first, second])

    assert result["valid"] is False
    assert result["reason"] == "transition hash discontinuity"
    assert result["checked"] == 1


def test_transition_chain_rejects_event_hash_tampering():
    audit = _queue_audit_module()
    first = _event(
        audit,
        seq=1,
        from_status=None,
        to_status="queued",
        previous_hash=None,
        at="t1",
    )
    tampered = dict(first, actor="different-actor")

    result = audit.verify_transition_events([tampered])

    assert result["valid"] is False
    assert result["reason"] == "transition hash mismatch"
    assert result["checked"] == 0


def test_transition_builder_rejects_impossible_status_change():
    audit = _queue_audit_module()

    with pytest.raises(ValueError, match="invalid job transition"):
        _event(
            audit,
            seq=1,
            from_status="queued",
            to_status="completed",
            previous_hash=None,
            at="t1",
        )


def test_sqlite_queue_records_claim_and_completion_transitions(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue("campaign-1", "report", {"campaign_id": "campaign-1"})

    claimed = queue.claim("worker-a")
    assert claimed is not None
    assert claimed["id"] == job["id"]
    queue.finish(job["id"], "worker-a", True)

    events = queue.job_transitions(job["id"])
    assert [event["to_status"] for event in events] == [
        "queued",
        "running",
        "completed",
    ]
    assert queue.verify_job_transitions(job["id"])["valid"] is True


def test_sqlite_queue_records_retry_chain_without_raw_worker_error(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1"},
        max_attempts=2,
    )

    assert queue.claim("worker-a") is not None
    queue.finish(job["id"], "worker-a", False, "sensitive worker detail")
    assert queue.claim("worker-a") is not None
    queue.finish(job["id"], "worker-a", True)

    events = queue.job_transitions(job["id"])
    assert [event["to_status"] for event in events] == [
        "queued",
        "running",
        "queued",
        "running",
        "completed",
    ]
    assert "sensitive worker detail" not in json.dumps(events)
    assert queue.verify_job_transitions(job["id"])["valid"] is True


def test_sqlite_queue_records_queued_and_owned_cancellation(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    queued = queue.enqueue("campaign-queued", "report", {"campaign_id": "campaign-queued"})
    assert queue.cancel_queued("campaign-queued") == 1
    assert [event["to_status"] for event in queue.job_transitions(queued["id"])] == [
        "queued",
        "cancelled",
    ]

    running = queue.enqueue("campaign-running", "report", {"campaign_id": "campaign-running"})
    assert queue.claim("worker-a") is not None
    assert queue.cancel_owned(running["id"], "worker-a", "operator detail") is not None
    events = queue.job_transitions(running["id"])
    assert [event["to_status"] for event in events] == ["queued", "running", "cancelled"]
    assert "operator detail" not in json.dumps(events)


def test_sqlite_queue_records_expired_lease_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1"},
        max_attempts=2,
    )
    assert queue.claim("worker-a") is not None

    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with queue.connect() as db:
        db.execute("UPDATE jobs SET claimed_at=? WHERE id=?", (stale, job["id"]))

    assert queue.recover_expired_leases() == 1
    events = queue.job_transitions(job["id"])
    assert [event["to_status"] for event in events] == ["queued", "running", "queued"]
    assert queue.verify_job_transitions(job["id"])["valid"] is True


def test_sqlite_queue_detects_transition_tampering_and_missing_event(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue("campaign-1", "report", {"campaign_id": "campaign-1"})
    assert queue.claim("worker-a") is not None
    queue.finish(job["id"], "worker-a", True)

    with queue.connect() as db:
        db.execute(
            "UPDATE job_transitions SET actor='tampered' WHERE job_id=? AND seq=2",
            (job["id"],),
        )
    result = queue.verify_job_transitions(job["id"])
    assert result["valid"] is False
    assert result["reason"] == "transition hash mismatch"

    with queue.connect() as db:
        db.execute("DELETE FROM job_transitions WHERE job_id=? AND seq=2", (job["id"],))
    result = queue.verify_job_transitions(job["id"])
    assert result["valid"] is False


def test_sqlite_campaign_transition_audit_aggregates_invalid_jobs(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    good = queue.enqueue("campaign-1", "report", {"campaign_id": "campaign-1"})
    bad = queue.enqueue("campaign-1", "report", {"campaign_id": "campaign-1", "n": 2})
    assert queue.claim("worker-a") is not None
    queue.finish(good["id"], "worker-a", True)

    with queue.connect() as db:
        db.execute("DELETE FROM job_transitions WHERE job_id=?", (bad["id"],))

    result = queue.campaign_transition_audit("campaign-1")
    assert result["jobs"] == 2
    assert result["valid_jobs"] == 1
    assert result["invalid_jobs"] == 1
    assert result["valid"] is False
