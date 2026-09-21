import time
from datetime import datetime, timedelta, timezone

from app import worker_liveness


def test_worker_heartbeat_round_trip_is_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_ROOT", str(tmp_path))
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_MAX_AGE_SECONDS", "30")

    worker_liveness.write_worker_heartbeat("scanner")
    result = worker_liveness.worker_liveness("scanner")

    assert result["live"] is True
    assert result["role"] == "scanner"
    assert result["contains_secrets"] is False
    assert "worker_id" not in result


def test_missing_worker_heartbeat_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_ROOT", str(tmp_path))

    result = worker_liveness.worker_liveness("general")

    assert result["live"] is False
    assert result["reason"] == "heartbeat_missing"


def test_stale_worker_heartbeat_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_ROOT", str(tmp_path))
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_MAX_AGE_SECONDS", "10")
    observed = datetime.now(timezone.utc) - timedelta(seconds=20)
    (tmp_path / "scanner.json").write_text(
        '{"observed_at":"' + observed.isoformat() + '","role":"scanner","version":1}',
        encoding="utf-8",
    )

    result = worker_liveness.worker_liveness(
        "scanner",
        now=datetime.now(timezone.utc),
    )

    assert result["live"] is False
    assert result["reason"] == "heartbeat_stale"
    assert result["age_seconds"] >= 20


def test_invalid_heartbeat_configuration_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_ROOT", str(tmp_path))
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_MAX_AGE_SECONDS", "invalid")

    result = worker_liveness.worker_liveness_snapshot()

    assert result["general"]["live"] is False
    assert result["scanner"]["live"] is False
    assert result["general"]["reason"] == "heartbeat_configuration_invalid"
    assert result["contains_secrets"] is False

def test_background_heartbeat_stays_independent_from_job_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_ROOT", str(tmp_path))
    monkeypatch.setenv("XBOW_WORKER_HEARTBEAT_MAX_AGE_SECONDS", "5")

    stop = worker_liveness.start_worker_heartbeat("scanner")
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not (tmp_path / "scanner.json").exists():
            time.sleep(0.01)
        assert (tmp_path / "scanner.json").exists()
        result = worker_liveness.worker_liveness("scanner")
        assert result["live"] is True
    finally:
        stop.set()
