import json

from app.jobqueue import JobQueue
from app.main import app
from app.queue_audit import build_transition_event, verify_transition_events


def test_transition_chain_accepts_valid_lifecycle():
    first = build_transition_event(
        job_id="job-1",
        campaign_id="campaign-1",
        kind="report",
        seq=1,
        from_status=None,
        to_status="queued",
        actor="queue",
        reason="job enqueued",
        at="t1",
        previous_hash=None,
    )
    second = build_transition_event(
        job_id="job-1",
        campaign_id="campaign-1",
        kind="report",
        seq=2,
        from_status="queued",
        to_status="running",
        actor="worker-a",
        reason="job claimed",
        at="t2",
        previous_hash=first["event_hash"],
    )
    third = build_transition_event(
        job_id="job-1",
        campaign_id="campaign-1",
        kind="report",
        seq=3,
        from_status="running",
        to_status="completed",
        actor="worker-a",
        reason="job completed",
        at="t3",
        previous_hash=second["event_hash"],
    )

    result = verify_transition_events([first, second, third])

    assert result["valid"] is True
    assert result["checked"] == 3
    assert result["final_status"] == "completed"


def test_transition_chain_rejects_impossible_transition():
    first = build_transition_event(
        job_id="job-1",
        campaign_id="campaign-1",
        kind="report",
        seq=1,
        from_status=None,
        to_status="queued",
        actor="queue",
        reason="job enqueued",
        at="t1",
        previous_hash=None,
    )
    forged = dict(first)
    forged["seq"] = 2
    forged["from_status"] = "queued"
    forged["to_status"] = "completed"

    result = verify_transition_events([first, forged])

    assert result["valid"] is False
    assert result["reason"] in {"invalid status transition", "transition hash mismatch"}


def test_sqlite_queue_records_claim_and_completion_transitions(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1", "platform": "generic"},
    )
    claimed = queue.claim("worker-a")
    assert claimed is not None
    finished = queue.finish(job["id"], "worker-a", True)
    assert finished is not None

    events = queue.job_transitions(job["id"])

    assert [item["to_status"] for item in events] == [
        "queued",
        "running",
        "completed",
    ]
    verification = queue.verify_job_transitions(job["id"])
    assert verification["valid"] is True
    assert verification["final_status"] == "completed"


def test_sqlite_queue_records_requeue_then_success(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1", "platform": "generic"},
        max_attempts=2,
    )
    queue.claim("worker-a")
    requeued = queue.finish(job["id"], "worker-a", False, "sensitive detail")
    assert requeued is not None
    assert requeued["status"] == "queued"
    queue.claim("worker-b")
    queue.finish(job["id"], "worker-b", True)

    events = queue.job_transitions(job["id"])
    assert [item["to_status"] for item in events] == [
        "queued",
        "running",
        "queued",
        "running",
        "completed",
    ]
    assert "sensitive detail" not in json.dumps(events)
    assert queue.verify_job_transitions(job["id"])["valid"] is True


def test_transition_audit_detects_tampering(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue("campaign-1", "report", {"campaign_id": "campaign-1"})
    queue.claim("worker-a")
    queue.finish(job["id"], "worker-a", True)

    with queue.connect() as db:
        db.execute(
            "UPDATE job_transitions SET to_status='failed' WHERE job_id=? AND seq=3",
            (job["id"],),
        )

    result = queue.verify_job_transitions(job["id"])

    assert result["valid"] is False
    assert result["reason"] in {
        "transition hash mismatch",
        "audit final status does not match job status",
    }


def test_campaign_transition_audit_summarizes_invalid_jobs(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    good = queue.enqueue("campaign-1", "report", {"campaign_id": "campaign-1"})
    bad = queue.enqueue(
        "campaign-1",
        "independent_validation",
        {"campaign_id": "campaign-1", "finding_id": "f1"},
    )
    queue.claim("worker-a")
    queue.finish(good["id"], "worker-a", True)

    with queue.connect() as db:
        db.execute(
            "DELETE FROM job_transitions WHERE job_id=?",
            (bad["id"],),
        )

    result = queue.campaign_transition_audit("campaign-1")

    assert result["jobs"] == 2
    assert result["valid"] is False
    assert any(item["job_id"] == bad["id"] for item in result["invalid_jobs"])


def test_queue_transition_audit_routes_are_exposed():
    paths = app.openapi()["paths"]
    assert "/api/jobs/{job_id}/transitions" in paths
    assert "/api/campaigns/{campaign_id}/audit/queue-transitions" in paths
