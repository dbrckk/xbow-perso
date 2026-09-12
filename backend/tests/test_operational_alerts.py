import pytest

from app.main import app
from app.operational_alerts import build_operational_alerts


def test_operational_alerts_are_aggregate_only(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_FAILED_JOBS", "1")
    monkeypatch.setenv("XBOW_ALERT_QUEUED_JOBS", "3")
    monkeypatch.setenv("XBOW_ALERT_RUNNING_JOBS", "4")

    result = build_operational_alerts(
        {
            "jobs_by_status": {
                "failed": 2,
                "queued": 3,
                "running": 1,
            }
        }
    )

    assert result["status"] == "alert"
    assert result["read_only"] is True
    assert result["aggregate_only"] is True
    assert {item["code"] for item in result["alerts"]} == {
        "failed_jobs",
        "queue_backlog",
    }


def test_operational_alerts_ok_below_thresholds(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_FAILED_JOBS", "2")
    monkeypatch.setenv("XBOW_ALERT_QUEUED_JOBS", "5")
    monkeypatch.setenv("XBOW_ALERT_RUNNING_JOBS", "5")

    result = build_operational_alerts(
        {
            "jobs_by_status": {
                "failed": 1,
                "queued": 4,
                "running": 4,
            }
        }
    )

    assert result["status"] == "ok"
    assert result["alerts"] == []


def test_operational_alert_thresholds_fail_closed(monkeypatch):
    monkeypatch.setenv("XBOW_ALERT_FAILED_JOBS", "0")

    with pytest.raises(ValueError, match="XBOW_ALERT_FAILED_JOBS"):
        build_operational_alerts({"jobs_by_status": {}})


def test_alerts_route_is_exposed_under_authenticated_api():
    assert "/api/alerts" in app.openapi()["paths"]
