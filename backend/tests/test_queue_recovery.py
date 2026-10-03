from datetime import datetime, timedelta, timezone

from app.main import app
from app.queue_recovery import analyze_queue_recovery, queue_recovery_assessment


def _job(**overrides):
    payload = {
        "id": "job-1",
        "status": "queued",
        "attempts": 0,
        "max_attempts": 2,
        "claimed_by": None,
        "claimed_at": None,
    }
    payload.update(overrides)
    return payload


def test_queue_recovery_is_safe_for_consistent_snapshot():
    result = analyze_queue_recovery(
        [_job()],
        lease_seconds=60,
        total_jobs=1,
    )

    assert result["safe_to_resume"] is True
    assert result["issues_total"] == 0
    assert result["read_only"] is True
    assert result["automatic_requeue"] is False
    assert result["automatic_mutation"] is False
    assert result["payloads_exposed"] is False
    assert result["worker_identities_exposed"] is False


def test_queue_recovery_detects_expired_running_lease_without_leaking_owner():
    now = datetime.now(timezone.utc)
    result = analyze_queue_recovery(
        [
            _job(
                status="running",
                attempts=1,
                claimed_by="secret-worker-name",
                claimed_at=(now - timedelta(seconds=120)).isoformat(),
            )
        ],
        lease_seconds=60,
        total_jobs=1,
        now=now,
    )

    assert result["safe_to_resume"] is False
    assert any(item["code"] == "expired_running_lease" for item in result["issues"])
    assert "secret-worker-name" not in str(result)


def test_queue_recovery_detects_invalid_retry_and_stale_lease_fields():
    result = analyze_queue_recovery(
        [
            _job(
                status="completed",
                attempts=3,
                max_attempts=2,
                claimed_by="stale-worker",
                claimed_at="2026-10-03T12:00:00+00:00",
            )
        ],
        lease_seconds=60,
        total_jobs=1,
    )

    codes = {item["code"] for item in result["issues"]}
    assert "non_running_job_has_lease_fields" in codes
    assert "invalid_retry_state" in codes


def test_queue_recovery_detects_future_timestamp_and_unknown_status():
    now = datetime.now(timezone.utc)
    result = analyze_queue_recovery(
        [
            _job(
                status="running",
                attempts=1,
                claimed_by="worker",
                claimed_at=(now + timedelta(minutes=10)).isoformat(),
            ),
            _job(id="job-2", status="mystery"),
        ],
        lease_seconds=60,
        total_jobs=2,
        now=now,
    )

    codes = {item["code"] for item in result["issues"]}
    assert "claim_timestamp_in_future" in codes
    assert "unknown_status" in codes


def test_queue_recovery_fails_closed_when_snapshot_is_truncated():
    result = analyze_queue_recovery(
        [_job()],
        lease_seconds=60,
        total_jobs=2,
    )

    assert result["assessment_truncated"] is True
    assert result["safe_to_resume"] is False
    assert any(item["code"] == "assessment_truncated" for item in result["issues"])


def test_queue_recovery_route_is_exposed():
    assert "/api/recovery/queue" in app.openapi()["paths"]


def test_queue_recovery_route_never_returns_payloads_or_worker_identity(monkeypatch):
    class Backend:
        def health(self):
            return {"ok": True, "storage": "fixture"}

        def stats(self):
            return {"total": 1}

        def recovery_snapshot(self, limit=5000):
            assert limit == 5000
            return [
                {
                    "id": "job-1",
                    "status": "running",
                    "attempts": 1,
                    "max_attempts": 2,
                    "claimed_by": "private-worker",
                    "claimed_at": "2000-01-01T00:00:00+00:00",
                    "payload": {"secret": "must-not-leak"},
                }
            ]

    monkeypatch.setattr("app.main.queue", lambda: Backend())
    result = queue_recovery_assessment()

    assert result["payloads_exposed"] is False
    assert result["worker_identities_exposed"] is False
    assert "private-worker" not in str(result)
    assert "must-not-leak" not in str(result)



def test_queue_recovery_bounds_issue_details_but_keeps_exact_counts():
    jobs = [
        _job(
            id=f"job-{index}",
            status="queued",
            attempts=2,
            max_attempts=2,
        )
        for index in range(250)
    ]

    result = analyze_queue_recovery(
        jobs,
        lease_seconds=60,
        total_jobs=250,
    )

    assert result["issues_total"] == 250
    assert len(result["issues"]) == 200
    assert result["issue_details_truncated"] is True
    assert result["safe_to_resume"] is False



def test_queue_recovery_marks_unhealthy_storage_critical(monkeypatch):
    from app.queue_recovery import build_queue_recovery_assessment

    class Backend:
        def health(self):
            return {"ok": False, "storage": "fixture"}

        def stats(self):
            return {"total": 0}

        def recovery_snapshot(self, limit=5000):
            return []

    result = build_queue_recovery_assessment(Backend())

    assert result["storage_healthy"] is False
    assert result["safe_to_resume"] is False
    assert result["issues_by_severity"]["critical"] == 1
    assert any(item["code"] == "queue_storage_unhealthy" for item in result["issues"])
