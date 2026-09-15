from datetime import datetime, timedelta, timezone

from app.rolling_telemetry import build_rolling_telemetry


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def event(seconds_ago, status="completed", duration_ms=100):
    return {
        "type": "worker_outcome",
        "status": status,
        "duration_ms": duration_ms,
        "at": (NOW - timedelta(seconds=seconds_ago)).isoformat(),
    }


def test_rolling_windows_are_time_bounded():
    result = build_rolling_telemetry(
        [event(10), event(200, "failed"), event(900)],
        now=NOW,
    )
    assert result["windows"]["300"]["events"] == 2
    assert result["windows"]["3600"]["events"] == 3


def test_failure_rate_is_computed_per_window():
    result = build_rolling_telemetry(
        [event(10), event(20, "failed"), event(30, "failed")],
        now=NOW,
    )
    assert result["windows"]["300"]["failure_rate"] == 2 / 3


def test_latency_percentiles_use_bounded_durations():
    result = build_rolling_telemetry(
        [event(1, duration_ms=10), event(2, duration_ms=20), event(3, duration_ms=100)],
        now=NOW,
    )
    durations = result["windows"]["300"]["duration_ms"]
    assert durations["p50"] == 20
    assert durations["p95"] == 100
    assert durations["p99"] == 100


def test_future_and_malformed_events_are_ignored():
    future = event(-10)
    malformed = {"type": "worker_outcome", "status": "failed", "at": "bad"}
    result = build_rolling_telemetry([future, malformed, event(1)], now=NOW)
    assert result["windows"]["300"]["events"] == 1


def test_output_is_redacted():
    result = build_rolling_telemetry([event(1)], now=NOW)
    assert result["contains_targets"] is False
    assert result["contains_payloads"] is False
    assert result["contains_secrets"] is False
