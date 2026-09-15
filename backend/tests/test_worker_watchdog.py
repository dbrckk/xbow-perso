import pytest

from app.worker_watchdog import build_worker_watchdog


_ENV = (
    "XBOW_WATCHDOG_MAX_QUEUE_AGE_SECONDS",
    "XBOW_WATCHDOG_MAX_RUNNING_LEASE_AGE_SECONDS",
    "XBOW_WATCHDOG_MAX_FAILED_JOBS",
)


def _clear(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def test_watchdog_ok_for_healthy_aggregate_metrics(monkeypatch):
    _clear(monkeypatch)
    result = build_worker_watchdog({
        "oldest_queued_age_seconds": 10,
        "oldest_running_lease_age_seconds": 20,
        "jobs_by_status": {"failed": 0},
    })
    assert result["status"] == "ok"
    assert result["issues"] == []


def test_watchdog_detects_stalled_queue(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_WATCHDOG_MAX_QUEUE_AGE_SECONDS", "60")
    result = build_worker_watchdog({
        "oldest_queued_age_seconds": 61,
        "oldest_running_lease_age_seconds": 20,
        "jobs_by_status": {},
    })
    assert result["status"] == "warning"
    assert [item["code"] for item in result["issues"]] == ["queue_stalled"]


def test_watchdog_detects_stale_running_lease(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_WATCHDOG_MAX_RUNNING_LEASE_AGE_SECONDS", "60")
    result = build_worker_watchdog({
        "oldest_queued_age_seconds": 0,
        "oldest_running_lease_age_seconds": 61,
        "jobs_by_status": {},
    })
    assert result["status"] == "error"
    assert [item["code"] for item in result["issues"]] == ["running_lease_stale"]


def test_watchdog_enforces_failed_job_budget(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_WATCHDOG_MAX_FAILED_JOBS", "2")
    result = build_worker_watchdog({
        "oldest_queued_age_seconds": 0,
        "oldest_running_lease_age_seconds": 0,
        "jobs_by_status": {"failed": 3},
    })
    assert result["status"] == "warning"
    assert [item["code"] for item in result["issues"]] == ["failed_job_budget_exceeded"]


def test_watchdog_invalid_threshold_fails_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_WATCHDOG_MAX_QUEUE_AGE_SECONDS", "invalid")
    with pytest.raises(ValueError):
        build_worker_watchdog({"jobs_by_status": {}})
