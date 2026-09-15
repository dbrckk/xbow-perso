from app.metrics import build_operational_metrics
from app import readiness as readiness_module


class Queue:
    def health(self):
        return {"ok": True}

    def stats(self):
        return {
            "total": 2,
            "by_status": {"running": 1, "failed": 1},
            "oldest_queued_at": None,
            "oldest_running_claimed_at": None,
            "storage": "test",
        }


class Store:
    artifact_root = None

    def health(self):
        return {"ok": True}

    def list_campaigns(self):
        return []


def test_metrics_include_watchdog(monkeypatch):
    for name in (
        "XBOW_WATCHDOG_MAX_QUEUE_AGE_SECONDS",
        "XBOW_WATCHDOG_MAX_RUNNING_LEASE_AGE_SECONDS",
        "XBOW_WATCHDOG_MAX_FAILED_JOBS",
    ):
        monkeypatch.delenv(name, raising=False)

    result = build_operational_metrics(Queue(), Store())

    assert result["worker_watchdog"]["status"] == "ok"
    assert result["worker_watchdog"]["contains_payloads"] is False
    assert result["worker_watchdog"]["contains_secrets"] is False


def test_invalid_watchdog_config_is_redacted_error(monkeypatch):
    monkeypatch.setenv("XBOW_WATCHDOG_MAX_QUEUE_AGE_SECONDS", "invalid")

    result = build_operational_metrics(Queue(), Store())

    assert result["worker_watchdog"]["status"] == "error"
    assert result["worker_watchdog"]["issues"] == [
        {"code": "watchdog_configuration_invalid", "severity": "error"}
    ]


def test_readiness_fails_on_critical_watchdog(monkeypatch, tmp_path):
    queue = Queue()
    store = Store()
    store.artifact_root = tmp_path
    monkeypatch.setattr(readiness_module, "JobQueue", lambda: queue)
    monkeypatch.setattr(readiness_module, "Storage", lambda: store)
    monkeypatch.setenv("XBOW_WATCHDOG_MAX_RUNNING_LEASE_AGE_SECONDS", "60")

    def stale_stats():
        result = queue.stats()
        result["oldest_running_claimed_at"] = "2000-01-01T00:00:00+00:00"
        return result

    queue.stats = stale_stats
    result = readiness_module.readiness()

    assert result["ok"] is False
    assert result["worker_watchdog"]["status"] == "error"
