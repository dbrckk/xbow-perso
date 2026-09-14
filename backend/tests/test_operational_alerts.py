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



def test_operational_alerts_flag_recovery_block_and_regression(monkeypatch):
    result = build_operational_alerts(
        {
            "jobs_by_status": {
                "failed": 0,
                "queued": 0,
                "running": 0,
            },
            "recovery_readiness": {
                "latest_decision": "BLOCK",
                "ready_to_block_regressions": 1,
            },
        }
    )

    codes = {item["code"] for item in result["alerts"]}
    assert "recovery_readiness_block" in codes
    assert "recovery_ready_to_block_regression" in codes
    assert result["status"] == "alert"



def test_operational_alerts_flag_persistent_control_plane_degradation():
    result = build_operational_alerts(
        {
            "jobs_by_status": {"failed": 0, "queued": 0, "running": 0},
            "control_plane_health": {
                "latest_state": "BLOCKED",
                "delta": -12,
                "trend": "degrading",
                "persistent_degradation": True,
            },
        }
    )

    codes = {item["code"] for item in result["alerts"]}
    assert "control_plane_persistent_degradation" in codes
    assert "control_plane_health_degrading" in codes
    assert result["status"] == "alert"



def test_operational_alerts_flag_exhausted_slo_budget():
    result = build_operational_alerts(
        {
            "jobs_total": 1,
            "jobs_by_status": {"failed": 1, "queued": 0, "running": 0},
            "queue_transition_audit": {"valid": False},
            "recovery_readiness": {"latest_decision": "READY"},
            "control_plane_health": {"latest_score": 100},
            "pending_outbox_total": 0,
        }
    )

    codes = {item["code"] for item in result["alerts"]}
    assert "slo_error_budget_exhausted" in codes
    assert result["status"] == "alert"



def test_operational_alerts_flag_fast_multiwindow_slo_burn():
    result = build_operational_alerts(
        {
            "jobs_total": 10,
            "jobs_by_status": {"failed": 0, "queued": 0, "running": 0},
            "queue_transition_audit": {"valid": True},
            "recovery_readiness": {"latest_decision": "READY"},
            "control_plane_health": {"latest_score": 100},
            "pending_outbox_total": 0,
            "slo": {
                "state": "HEALTHY",
                "summary": {
                    "exhausted_slos": [],
                    "at_risk_slos": [],
                },
                "historical": {
                    "windows": {
                        "1h": {"burn_rate": 2.5},
                        "24h": {"burn_rate": 1.2},
                        "7d": {"burn_rate": 0.8},
                    }
                },
                "multiwindow_policy": {
                    "fast_burn": {
                        "triggered": True,
                        "thresholds": {"1h": 2.0, "24h": 1.0},
                    },
                    "slow_burn": {"triggered": False},
                },
            },
        }
    )

    codes = {item["code"] for item in result["alerts"]}
    assert "slo_fast_burn_multiwindow" in codes
    assert result["status"] == "alert"


def test_operational_alerts_flag_slow_multiwindow_slo_burn():
    result = build_operational_alerts(
        {
            "jobs_total": 10,
            "jobs_by_status": {"failed": 0, "queued": 0, "running": 0},
            "queue_transition_audit": {"valid": True},
            "recovery_readiness": {"latest_decision": "READY"},
            "control_plane_health": {"latest_score": 100},
            "pending_outbox_total": 0,
            "slo": {
                "state": "HEALTHY",
                "summary": {
                    "exhausted_slos": [],
                    "at_risk_slos": [],
                },
                "historical": {
                    "windows": {
                        "1h": {"burn_rate": 0.5},
                        "24h": {"burn_rate": 1.1},
                        "7d": {"burn_rate": 1.0},
                    }
                },
                "multiwindow_policy": {
                    "fast_burn": {"triggered": False},
                    "slow_burn": {
                        "triggered": True,
                        "thresholds": {"24h": 1.0, "7d": 1.0},
                    },
                },
            },
        }
    )

    codes = {item["code"] for item in result["alerts"]}
    assert "slo_slow_burn_multiwindow" in codes
    assert result["status"] == "alert"



def test_operational_alerts_do_not_page_on_partial_multiwindow_data():
    result = build_operational_alerts(
        {
            "jobs_by_status": {"failed": 0, "queued": 0, "running": 0},
            "slo": {
                "state": "HEALTHY",
                "summary": {"exhausted_slos": [], "at_risk_slos": []},
                "historical": {
                    "windows": {
                        "1h": {"burn_rate": 3.0},
                        "24h": {"burn_rate": 2.0},
                        "7d": {"burn_rate": 1.5},
                    }
                },
                "multiwindow_policy": {
                    "fast_burn": {"triggered": False},
                    "slow_burn": {"triggered": False},
                },
            },
        }
    )

    codes = {item["code"] for item in result["alerts"]}
    assert "slo_fast_burn_multiwindow" not in codes
    assert "slo_slow_burn_multiwindow" not in codes



def test_operational_alerts_flag_invalid_submission_audit():
    result = build_operational_alerts(
        {
            "jobs_by_status": {
                "failed": 0,
                "queued": 0,
                "running": 0,
            },
            "submission_integrity": {
                "supported": True,
                "valid": False,
                "invalid_reports": 2,
                "issue_class_counts": {
                    "structural": 1,
                    "stale": 1,
                },
                "severity": {
                    "highest": "high",
                    "counts": {
                        "high": 1,
                        "medium": 0,
                        "low": 1,
                    },
                    "weighted_score": 4,
                },
            },
        }
    )

    alerts = {
        item["code"]: item
        for item in result["alerts"]
    }
    assert alerts["submission_event_audit_invalid"]["severity"] == "warning"
    assert alerts["submission_event_audit_invalid"]["value"] == {
        "invalid_reports": 2,
        "issue_class_counts": {
            "structural": 1,
            "stale": 1,
        },
        "severity": {
            "highest": "high",
            "counts": {
                "high": 1,
                "medium": 0,
                "low": 1,
            },
            "weighted_score": 4,
        },
    }
