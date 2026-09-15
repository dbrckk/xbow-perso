import pytest

from app.operational_slo import build_operational_slo


def base_metrics():
    return {
        "oldest_queued_age_seconds": 0,
        "oldest_outbox_pending_age_seconds": 0,
        "jobs_by_status": {"failed": 0},
        "worker_watchdog": {"status": "ok"},
    }


def test_slo_healthy_by_default(monkeypatch):
    result = build_operational_slo(base_metrics())
    assert result["state"] == "healthy"
    assert result["signals"] == []


def test_slo_degraded_on_warning_queue_age(monkeypatch):
    metrics = base_metrics()
    metrics["oldest_queued_age_seconds"] = 120
    result = build_operational_slo(metrics)
    assert result["state"] == "degraded"


def test_slo_critical_on_queue_age(monkeypatch):
    metrics = base_metrics()
    metrics["oldest_queued_age_seconds"] = 600
    result = build_operational_slo(metrics)
    assert result["state"] == "critical"


def test_slo_critical_when_watchdog_errors(monkeypatch):
    metrics = base_metrics()
    metrics["worker_watchdog"] = {"status": "error"}
    result = build_operational_slo(metrics)
    assert result["state"] == "critical"


def test_slo_rejects_inverted_thresholds(monkeypatch):
    monkeypatch.setenv("XBOW_SLO_WARN_QUEUE_AGE_SECONDS", "700")
    monkeypatch.setenv("XBOW_SLO_CRITICAL_QUEUE_AGE_SECONDS", "600")
    with pytest.raises(ValueError):
        build_operational_slo(base_metrics())
