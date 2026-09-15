import pytest

from app.observer_heartbeat import with_lease_heartbeat
from app.observer_lease import ObserverLease
from app.observer_scheduler import run_scheduled_observation, scheduler_config


def test_deadline_must_be_below_lease_ttl(monkeypatch):
    monkeypatch.setenv("XBOW_INCIDENT_OBSERVER_INTERVAL_SECONDS", "10")
    monkeypatch.setenv("XBOW_INCIDENT_OBSERVER_LEASE_TTL_SECONDS", "20")
    monkeypatch.setenv("XBOW_INCIDENT_OBSERVER_DEADLINE_SECONDS", "20")
    with pytest.raises(ValueError):
        scheduler_config()


def test_scheduler_reports_deadline_exceeded(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_INCIDENT_OBSERVER_INTERVAL_SECONDS", "10")
    monkeypatch.setenv("XBOW_INCIDENT_OBSERVER_LEASE_TTL_SECONDS", "20")
    monkeypatch.setenv("XBOW_INCIDENT_OBSERVER_DEADLINE_SECONDS", "5")
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))

    import app.observer_scheduler as scheduler
    values = iter([0.0, 6.0])
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: next(values))

    result = run_scheduled_observation(
        lease, "node-a", lambda owner, generation: {"ok": True}
    )
    assert result["ran"] is False
    assert result["reason"] == "deadline_exceeded"


def test_heartbeat_preserves_current_generation(tmp_path):
    path = str(tmp_path / "lease.sqlite3")
    lease = ObserverLease(path)
    generation = lease.acquire("node-a", ttl_seconds=10)

    result = with_lease_heartbeat(
        lease,
        "node-a",
        generation,
        10,
        lambda: "done",
    )
    assert result == "done"
    assert lease.is_current("node-a", generation) is True
