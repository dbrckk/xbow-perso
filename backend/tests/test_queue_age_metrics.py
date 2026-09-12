from datetime import datetime, timedelta, timezone

from app.metrics import build_operational_metrics
from app.operational_alerts import build_operational_alerts


class Queue:
    def __init__(self, oldest):
        self.oldest = oldest

    def stats(self):
        return {
            "total": 3,
            "by_status": {"queued": 2, "running": 1},
            "storage": "redis",
            "oldest_queued_at": self.oldest,
        }


class Storage:
    def list_campaigns(self):
        return [{"state": "running"}]


def test_metrics_expose_queue_age_without_payloads():
    oldest = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    metrics = build_operational_metrics(Queue(oldest), Storage())
    assert 115 <= metrics["oldest_queued_age_seconds"] <= 125
    assert metrics["queue_storage"] == "redis"
    assert metrics["contains_payloads"] is False
    assert metrics["contains_secrets"] is False


def test_invalid_queue_timestamp_does_not_break_metrics():
    metrics = build_operational_metrics(Queue("not-a-date"), Storage())
    assert metrics["oldest_queued_age_seconds"] is None


def test_alerts_detect_stalled_queue(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_QUEUE_AGE_SECONDS", "60")
    result = build_operational_alerts(
        {
            "jobs_by_status": {"failed": 0, "queued": 1, "running": 0},
            "oldest_queued_age_seconds": 61,
        }
    )
    stalled = [item for item in result["alerts"] if item["code"] == "queue_stalled"]
    assert stalled == [{"code": "queue_stalled", "severity": "critical", "value": 61, "threshold": 60}]


def test_queue_age_threshold_fails_closed_on_invalid_config(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_QUEUE_AGE_SECONDS", "10")
    try:
        build_operational_alerts({"jobs_by_status": {}})
    except ValueError as exc:
        assert "XBOW_ALERT_QUEUE_AGE_SECONDS" in str(exc)
    else:
        raise AssertionError("invalid alert threshold was accepted")


def test_overflowing_queue_timestamp_does_not_break_metrics():
    metrics = build_operational_metrics(
        Queue("9999-12-31T23:59:59-01:00"),
        Storage(),
    )
    assert metrics["oldest_queued_age_seconds"] is None
