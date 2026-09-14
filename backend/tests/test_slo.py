from app.main import app
from app.slo import build_platform_slos


def _metrics():
    return {
        "jobs_total": 10,
        "jobs_by_status": {
            "completed": 10,
            "failed": 0,
            "cancelled": 0,
        },
        "queue_transition_audit": {"valid": True},
        "recovery_readiness": {"latest_decision": "READY"},
        "control_plane_health": {"latest_score": 100},
        "pending_outbox_total": 0,
    }


def test_platform_slos_are_healthy_when_signals_are_clean():
    result = build_platform_slos(_metrics())

    assert result["state"] == "HEALTHY"
    assert result["summary"]["healthy"] == 5
    assert result["summary"]["at_risk"] == 0
    assert result["summary"]["exhausted"] == 0
    assert result["read_only"] is True
    assert result["automatic_mutation"] is False
    assert result["automatic_worker_control"] is False


def test_platform_slos_exhaust_queue_integrity_on_invalid_audit():
    metrics = _metrics()
    metrics["queue_transition_audit"]["valid"] = False

    result = build_platform_slos(metrics)
    queue = next(item for item in result["slos"] if item["name"] == "queue_integrity")

    assert queue["state"] == "EXHAUSTED"
    assert queue["observed"] == 0.0
    assert "queue_integrity" in result["summary"]["exhausted_slos"]
    assert result["state"] == "EXHAUSTED"


def test_platform_slos_mark_job_reliability_at_risk():
    metrics = _metrics()
    metrics["jobs_by_status"] = {
        "completed": 98,
        "failed": 1,
        "cancelled": 1,
    }
    metrics["jobs_total"] = 100

    result = build_platform_slos(metrics)
    reliability = next(item for item in result["slos"] if item["name"] == "job_reliability")

    assert reliability["observed"] == 0.98
    assert reliability["budget_consumed"] == 1.0
    assert reliability["state"] == "AT_RISK"


def test_platform_slos_block_recovery_budget_when_gate_blocks():
    metrics = _metrics()
    metrics["recovery_readiness"]["latest_decision"] = "BLOCK"

    result = build_platform_slos(metrics)
    recovery = next(item for item in result["slos"] if item["name"] == "recovery_readiness")

    assert recovery["state"] == "EXHAUSTED"
    assert recovery["observed"] == 0.0


def test_platform_slos_route_is_exposed():
    assert "/api/slo" in app.openapi()["paths"]
