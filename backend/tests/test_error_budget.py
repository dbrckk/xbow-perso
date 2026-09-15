import pytest

from app.error_budget import build_error_budget_status


def telemetry(short_rate, long_rate, short_events=100, long_events=1000):
    return {
        "windows": {
            "300": {"failure_rate": short_rate, "events": short_events},
            "3600": {"failure_rate": long_rate, "events": long_events},
        }
    }


def test_error_budget_is_healthy_with_low_failure_rates(monkeypatch):
    monkeypatch.delenv("XBOW_SLO_TARGET_SUCCESS_RATE", raising=False)
    result = build_error_budget_status(telemetry(0.001, 0.002))
    assert result["state"] == "healthy"


def test_fast_multiwindow_burn_is_critical(monkeypatch):
    monkeypatch.delenv("XBOW_SLO_TARGET_SUCCESS_RATE", raising=False)
    result = build_error_budget_status(telemetry(0.15, 0.07))
    assert result["state"] == "critical"
    assert result["alerts"][0]["code"] == "fast_error_budget_burn"


def test_elevated_multiwindow_burn_is_degraded(monkeypatch):
    monkeypatch.delenv("XBOW_SLO_TARGET_SUCCESS_RATE", raising=False)
    result = build_error_budget_status(telemetry(0.07, 0.04))
    assert result["state"] == "degraded"


def test_low_sample_volume_does_not_page(monkeypatch):
    monkeypatch.delenv("XBOW_SLO_TARGET_SUCCESS_RATE", raising=False)
    result = build_error_budget_status(
        telemetry(1.0, 1.0, short_events=1, long_events=2)
    )
    assert result["state"] == "healthy"
    assert result["alerts"] == []


def test_invalid_success_target_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_SLO_TARGET_SUCCESS_RATE", "1.0")
    with pytest.raises(ValueError):
        build_error_budget_status(telemetry(0, 0))
