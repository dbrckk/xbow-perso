from datetime import datetime, timedelta, timezone

from app.jobqueue import JobQueue
from app.main import app
from app.queue_recovery import analyze_queue_recovery


def test_recovery_assessment_is_safe_for_consistent_queue(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1"},
    )
    queue.claim("worker-a")
    queue.finish(job["id"], "worker-a", True)

    result = queue.recovery_assessment()

    assert result["safe_to_resume"] is True
    assert result["issues_total"] == 0
    assert result["automatic_requeue"] is False
    assert result["automatic_job_creation"] is False
    assert result["automatic_mutation"] is False


def test_recovery_assessment_detects_running_job_without_owner():
    now = datetime.now(timezone.utc)
    result = analyze_queue_recovery(
        [
            {
                "id": "job-1",
                "status": "running",
                "attempts": 1,
                "max_attempts": 2,
                "claimed_by": None,
                "claimed_at": now.isoformat(),
            }
        ],
        lease_seconds=60,
        audit_results={"job-1": {"valid": True}},
        now=now,
    )

    assert result["safe_to_resume"] is False
    assert any(item["code"] == "running_without_owner" for item in result["issues"])


def test_recovery_assessment_detects_expired_running_lease():
    now = datetime.now(timezone.utc)
    result = analyze_queue_recovery(
        [
            {
                "id": "job-1",
                "status": "running",
                "attempts": 1,
                "max_attempts": 2,
                "claimed_by": "worker-a",
                "claimed_at": (now - timedelta(seconds=120)).isoformat(),
            }
        ],
        lease_seconds=60,
        audit_results={"job-1": {"valid": True}},
        now=now,
    )

    assert result["safe_to_resume"] is False
    issue = next(item for item in result["issues"] if item["code"] == "expired_running_lease")
    assert issue["severity"] == "warning"
    assert issue["recommended_action"] == "review_lease_recovery"


def test_recovery_assessment_detects_non_running_lease_fields():
    now = datetime.now(timezone.utc)
    result = analyze_queue_recovery(
        [
            {
                "id": "job-1",
                "status": "completed",
                "attempts": 1,
                "max_attempts": 2,
                "claimed_by": "stale-worker",
                "claimed_at": now.isoformat(),
            }
        ],
        lease_seconds=60,
        audit_results={"job-1": {"valid": True}},
        now=now,
    )

    assert result["safe_to_resume"] is False
    assert any(
        item["code"] == "non_running_job_has_lease_fields"
        for item in result["issues"]
    )


def test_recovery_assessment_detects_invalid_retry_state():
    result = analyze_queue_recovery(
        [
            {
                "id": "job-1",
                "status": "failed",
                "attempts": 3,
                "max_attempts": 2,
                "claimed_by": None,
                "claimed_at": None,
            }
        ],
        lease_seconds=60,
        audit_results={"job-1": {"valid": True}},
    )

    assert any(item["code"] == "invalid_retry_state" for item in result["issues"])


def test_recovery_assessment_detects_invalid_transition_audit():
    result = analyze_queue_recovery(
        [
            {
                "id": "job-1",
                "status": "queued",
                "attempts": 0,
                "max_attempts": 2,
                "claimed_by": None,
                "claimed_at": None,
            }
        ],
        lease_seconds=60,
        audit_results={"job-1": {"valid": False}},
    )

    assert any(item["code"] == "transition_audit_invalid" for item in result["issues"])
    assert result["automatic_requeue"] is False


def test_sqlite_recovery_assessment_detects_audit_deletion(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1"},
    )
    with queue.connect() as db:
        db.execute("DELETE FROM job_transitions WHERE job_id=?", (job["id"],))

    result = queue.recovery_assessment()

    assert result["safe_to_resume"] is False
    assert any(
        item["job_id"] == job["id"] and item["code"] == "transition_audit_invalid"
        for item in result["issues"]
    )


def test_queue_recovery_route_is_exposed():
    assert "/api/recovery/queue" in app.openapi()["paths"]
