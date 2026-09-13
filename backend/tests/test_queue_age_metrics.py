from datetime import datetime, timedelta, timezone

from app.metrics import build_operational_metrics
from app.operational_alerts import build_operational_alerts


class Queue:
    def __init__(self, oldest, running=None):
        self.oldest = oldest
        self.running = running

    def stats(self):
        return {
            "total": 3,
            "by_status": {"queued": 2, "running": 1},
            "storage": "redis",
            "oldest_queued_at": self.oldest,
            "oldest_running_claimed_at": self.running,
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



class OutboxStorage:
    def __init__(self, requested_at):
        self.requested_at = requested_at

    def list_campaigns(self):
        return [
            {
                "state": "running",
                "events": [
                    {
                        "type": "report_requested",
                        "request_id": "secret-manual-report-id",
                        "platform": "generic",
                        "purpose": "manual",
                        "at": self.requested_at,
                    },
                    {
                        "type": "validation_requested",
                        "request_id": "validation:f1",
                        "finding_id": "f1",
                        "at": self.requested_at,
                    },
                    {
                        "type": "validation_queued",
                        "request_id": "validation:f1",
                        "finding_id": "f1",
                        "job_id": "job-validation",
                        "at": self.requested_at,
                    },
                ],
            }
        ]


def test_metrics_expose_outbox_age_and_counts_without_identities():
    requested_at = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    metrics = build_operational_metrics(Queue(None), OutboxStorage(requested_at))

    assert metrics["pending_outbox_total"] == 1
    assert metrics["pending_outbox_by_kind"] == {"report_manual": 1}
    assert 115 <= metrics["oldest_outbox_pending_age_seconds"] <= 125
    assert metrics["contains_outbox_identities"] is False
    rendered = str(metrics)
    assert "secret-manual-report-id" not in rendered
    assert "validation:f1" not in rendered


def test_alerts_detect_stalled_outbox(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_OUTBOX_AGE_SECONDS", "60")
    monkeypatch.setenv("XBOW_ALERT_PENDING_OUTBOX", "20")
    result = build_operational_alerts(
        {
            "jobs_by_status": {"failed": 0, "queued": 0, "running": 0},
            "pending_outbox_total": 1,
            "oldest_outbox_pending_age_seconds": 61,
        }
    )

    stalled = [item for item in result["alerts"] if item["code"] == "outbox_stalled"]
    assert stalled == [
        {
            "code": "outbox_stalled",
            "severity": "critical",
            "value": 61,
            "threshold": 60,
        }
    ]


def test_alerts_detect_outbox_backlog(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_PENDING_OUTBOX", "2")
    monkeypatch.setenv("XBOW_ALERT_OUTBOX_AGE_SECONDS", "300")
    result = build_operational_alerts(
        {
            "jobs_by_status": {"failed": 0, "queued": 0, "running": 0},
            "pending_outbox_total": 2,
            "oldest_outbox_pending_age_seconds": 10,
        }
    )

    backlog = [item for item in result["alerts"] if item["code"] == "outbox_backlog"]
    assert backlog == [
        {
            "code": "outbox_backlog",
            "severity": "warning",
            "value": 2,
            "threshold": 2,
        }
    ]


def test_outbox_alert_thresholds_fail_closed(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_OUTBOX_AGE_SECONDS", "10")

    try:
        build_operational_alerts({"jobs_by_status": {}})
    except ValueError as exc:
        assert "XBOW_ALERT_OUTBOX_AGE_SECONDS" in str(exc)
    else:
        raise AssertionError("invalid outbox alert threshold was accepted")



def test_metrics_expose_running_lease_age():
    running = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    metrics = build_operational_metrics(Queue(None, running), Storage())

    assert 115 <= metrics["oldest_running_lease_age_seconds"] <= 125


def test_invalid_running_lease_timestamp_does_not_break_metrics():
    metrics = build_operational_metrics(Queue(None, "not-a-date"), Storage())

    assert metrics["oldest_running_lease_age_seconds"] is None


def test_alerts_detect_stale_running_lease(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_RUNNING_LEASE_AGE_SECONDS", "60")
    result = build_operational_alerts(
        {
            "jobs_by_status": {"failed": 0, "queued": 0, "running": 1},
            "oldest_running_lease_age_seconds": 61,
        }
    )

    stale = [
        item
        for item in result["alerts"]
        if item["code"] == "running_lease_stale"
    ]
    assert stale == [
        {
            "code": "running_lease_stale",
            "severity": "critical",
            "value": 61,
            "threshold": 60,
        }
    ]


def test_running_lease_alert_threshold_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_RUNNING_LEASE_AGE_SECONDS", "10")

    try:
        build_operational_alerts({"jobs_by_status": {}})
    except ValueError as exc:
        assert "XBOW_ALERT_RUNNING_LEASE_AGE_SECONDS" in str(exc)
    else:
        raise AssertionError("invalid running lease alert threshold was accepted")
