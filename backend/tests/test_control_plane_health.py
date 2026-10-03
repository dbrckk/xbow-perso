from app.control_plane_health import build_control_plane_health
from app.main import app


def _healthy_metrics():
    return {
        "jobs_by_status": {
            "failed": 0,
            "queued": 0,
            "running": 0,
            "completed": 10,
        },
        "invalid_campaign_audit_chains": 0,
        "campaigns_with_legacy_audit_events": 0,
        "queue_recovery_available": True,
        "queue_recovery_safe_to_resume": True,
        "queue_recovery_critical_issues": 0,
        "queue_recovery_warning_issues": 0,
        "queue_recovery_assessment_truncated": False,
        "pending_outbox_total": 0,
        "oldest_outbox_pending_age_seconds": None,
        "worker_watchdog": {
            "status": "ok",
            "issues": [],
        },
    }


def test_control_plane_health_is_healthy_when_all_domains_are_clean():
    result = build_control_plane_health(
        _healthy_metrics(),
        {"status": "ok", "alerts": []},
    )

    assert result["status"] == "HEALTHY"
    assert result["score"] == 100.0
    assert result["hard_blockers"] == []
    assert all(
        item["status"] == "HEALTHY"
        for item in result["domains"].values()
    )
    assert result["read_only"] is True
    assert result["aggregate_only"] is True
    assert result["automatic_repair"] is False
    assert result["automatic_execution_change"] is False


def test_control_plane_health_degrades_without_hard_blocker():
    metrics = _healthy_metrics()
    metrics["queue_recovery_warning_issues"] = 1
    metrics["queue_recovery_safe_to_resume"] = False
    metrics["worker_watchdog"] = {
        "status": "warning",
        "issues": [
            {
                "code": "failed_job_budget_exceeded",
                "severity": "warning",
            }
        ],
    }
    alerts = {
        "status": "alert",
        "alerts": [
            {
                "code": "queue_backlog",
                "severity": "warning",
                "value": 30,
                "threshold": 20,
            },
            {
                "code": "outbox_backlog",
                "severity": "warning",
                "value": 25,
                "threshold": 20,
            },
        ],
    }

    result = build_control_plane_health(metrics, alerts)

    assert result["status"] == "DEGRADED"
    assert 39 < result["score"] < 85
    assert result["hard_blockers"] == []
    assert result["domains"]["queue_integrity"]["status"] == "DEGRADED"
    assert result["domains"]["worker_runtime"]["status"] == "DEGRADED"


def test_control_plane_health_blocks_on_invalid_campaign_audit():
    metrics = _healthy_metrics()
    metrics["invalid_campaign_audit_chains"] = 1

    result = build_control_plane_health(metrics, {"status": "ok", "alerts": []})

    assert result["status"] == "BLOCKED"
    assert result["score"] <= 39
    assert "campaign_audit_invalid" in result["hard_blockers"]
    assert result["domains"]["governance"]["status"] == "BLOCKED"


def test_control_plane_health_blocks_on_critical_queue_inconsistency():
    metrics = _healthy_metrics()
    metrics["queue_recovery_critical_issues"] = 2
    metrics["queue_recovery_safe_to_resume"] = False

    result = build_control_plane_health(
        metrics,
        {
            "status": "alert",
            "alerts": [
                {
                    "code": "queue_consistency_invalid",
                    "severity": "critical",
                    "value": 2,
                    "threshold": 1,
                }
            ],
        },
    )

    assert result["status"] == "BLOCKED"
    assert result["score"] <= 39
    assert "queue_consistency_invalid" in result["hard_blockers"]
    assert result["domains"]["queue_integrity"]["status"] == "BLOCKED"


def test_control_plane_health_blocks_when_alert_configuration_is_invalid():
    result = build_control_plane_health(
        _healthy_metrics(),
        {
            "status": "alert",
            "alerts": [
                {
                    "code": "alert_configuration_invalid",
                    "severity": "critical",
                    "value": 1,
                    "threshold": 1,
                }
            ],
        },
    )

    assert result["status"] == "BLOCKED"
    assert "alert_configuration_invalid" in result["hard_blockers"]
    assert result["alert_counts"]["critical"] == 1


def test_control_plane_health_does_not_echo_sensitive_input_fields():
    metrics = _healthy_metrics()
    metrics["private_target"] = "https://secret.example"
    metrics["payload"] = {"authorization": "super-secret"}
    metrics["worker_identity"] = "worker-private-123"

    result = build_control_plane_health(metrics, {"status": "ok", "alerts": []})
    rendered = str(result)

    assert "secret.example" not in rendered
    assert "super-secret" not in rendered
    assert "worker-private-123" not in rendered
    assert result["contains_targets"] is False
    assert result["contains_payloads"] is False
    assert result["contains_secrets"] is False
    assert result["contains_worker_identities"] is False


def test_control_plane_health_route_is_registered():
    assert "/api/operations/health" in app.openapi()["paths"]
