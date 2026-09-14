from app.control_plane_health import build_control_plane_health
from app.operations_dashboard import build_operations_dashboard


def _dashboard():
    return {
        "health": "HEALTHY",
        "blocked_reasons": [],
        "degraded_reasons": [],
        "summary": {
            "failed_jobs": 0,
            "pending_outbox_total": 0,
            "critical_alerts": 0,
            "warning_alerts": 0,
        },
        "recovery": {
            "latest_decision": "READY",
            "ready_to_block_regressions": 0,
        },
        "queue_integrity": {
            "storage": "sqlite",
            "audit_valid": True,
            "audit_invalid_jobs": 0,
        },
        "alerts": [],
    }


def test_control_plane_health_is_healthy_when_all_signals_are_clean():
    result = build_control_plane_health(_dashboard())

    assert result["score"] == 100
    assert result["state"] == "HEALTHY"
    assert all(
        component["score"] == 100
        for component in result["components"].values()
    )
    assert result["hard_blockers"] == []


def test_control_plane_health_caps_on_queue_audit_failure():
    dashboard = _dashboard()
    dashboard["queue_integrity"]["audit_valid"] = False
    dashboard["queue_integrity"]["audit_invalid_jobs"] = 1

    result = build_control_plane_health(dashboard)

    assert result["score"] <= 49
    assert result["state"] == "BLOCKED"
    assert result["components"]["queue"]["score"] == 0
    assert "queue_transition_audit_invalid" in result["hard_blockers"]


def test_control_plane_health_caps_on_recovery_block():
    dashboard = _dashboard()
    dashboard["recovery"]["latest_decision"] = "BLOCK"

    result = build_control_plane_health(dashboard)

    assert result["score"] <= 49
    assert result["state"] == "BLOCKED"
    assert result["components"]["recovery"]["score"] == 0
    assert "recovery_blocked" in result["hard_blockers"]


def test_control_plane_health_degrades_on_review():
    dashboard = _dashboard()
    dashboard["health"] = "DEGRADED"
    dashboard["degraded_reasons"] = ["recovery_operator_review_required"]
    dashboard["recovery"]["latest_decision"] = "REVIEW"

    result = build_control_plane_health(dashboard)

    assert result["components"]["recovery"]["score"] == 70
    assert result["components"]["recovery"]["state"] == "DEGRADED"
    assert result["score"] < 100


def test_control_plane_health_score_is_bounded():
    dashboard = _dashboard()
    dashboard["summary"]["failed_jobs"] = 999
    dashboard["summary"]["pending_outbox_total"] = 999
    dashboard["summary"]["critical_alerts"] = 999
    dashboard["summary"]["warning_alerts"] = 999
    dashboard["health"] = "BLOCKED"

    result = build_control_plane_health(dashboard)

    assert 0 <= result["score"] <= 100
    assert all(
        0 <= component["score"] <= 100
        for component in result["components"].values()
    )


def test_operations_dashboard_exposes_control_plane_health():
    class Queue:
        def stats(self):
            return {
                "total": 0,
                "storage": "sqlite",
                "by_status": {},
            }

        def campaign_transition_audit(self, campaign_id):
            return {
                "valid": True,
                "events": 0,
                "invalid_jobs": [],
            }

    class Storage:
        def list_campaigns(self):
            return []

        def list_recovery_readiness_snapshots(self, limit=100):
            return [{"decision": "READY"}]

    result = build_operations_dashboard(Queue(), Storage())

    assert "control_plane_health" in result
    assert result["control_plane_health"]["score"] == 100
