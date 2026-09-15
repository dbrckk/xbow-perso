from app.observer_slo import build_observer_slo


def test_observer_slo_healthy_by_default():
    assert build_observer_slo({})["state"] == "healthy"


def test_failure_streak_degrades_then_becomes_critical():
    assert build_observer_slo({"consecutive_failures": 1})["state"] == "degraded"
    assert build_observer_slo({"consecutive_failures": 3})["state"] == "critical"


def test_stale_success_is_critical():
    result = build_observer_slo({"last_success_age_seconds": 301})
    assert result["state"] == "critical"
    assert "observer_stale_success" in result["reasons"]


def test_circuit_open_is_critical():
    assert build_observer_slo({"circuit_open": True})["state"] == "critical"


def test_deadline_or_leadership_loss_degrades():
    assert build_observer_slo({"deadline_exceeded_count": 1})["state"] == "degraded"
    assert build_observer_slo({"leadership_lost_count": 1})["state"] == "degraded"
