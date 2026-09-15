from datetime import datetime, timedelta, timezone

import pytest

from app.observer_lease import ObserverLease
from app.observer_scheduler import run_scheduled_observation, scheduler_config


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def test_only_one_owner_holds_active_lease(tmp_path):
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
    assert lease.acquire("one", ttl_seconds=90, now=NOW) == 1
    assert lease.acquire("two", ttl_seconds=90, now=NOW) is None


def test_expired_lease_can_be_taken_over(tmp_path):
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
    assert lease.acquire("one", ttl_seconds=10, now=NOW) == 1
    assert lease.acquire("two", ttl_seconds=10, now=NOW + timedelta(seconds=11)) == 2


def test_scheduler_runs_only_for_leader(tmp_path):
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
    lease.acquire("other", ttl_seconds=90, now=datetime.now(timezone.utc))
    called = []
    result = run_scheduled_observation(lease, "me", lambda owner, generation: called.append((owner, generation)) or {"ok": True})
    assert result["ran"] is False
    assert result["reason"] == "not_leader"
    assert called == []


def test_scheduler_releases_lease_after_pass(tmp_path):
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
    result = run_scheduled_observation(lease, "me", lambda owner, generation: {"ok": True})
    assert result["ran"] is True
    assert lease.acquire("other", ttl_seconds=90) == 2


def test_invalid_scheduler_config_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_INCIDENT_OBSERVER_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("XBOW_INCIDENT_OBSERVER_LEASE_TTL_SECONDS", "30")
    with pytest.raises(ValueError):
        scheduler_config()
