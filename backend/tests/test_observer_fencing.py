from datetime import datetime, timedelta, timezone

from app.observer_lease import ObserverLease


NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def test_generation_increases_after_failover(tmp_path):
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
    first = lease.acquire("one", ttl_seconds=10, now=NOW)
    second = lease.acquire("two", ttl_seconds=10, now=NOW + timedelta(seconds=11))
    assert first == 1
    assert second == 2


def test_stale_generation_cannot_heartbeat(tmp_path):
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
    first = lease.acquire("one", ttl_seconds=10, now=NOW)
    lease.acquire("two", ttl_seconds=10, now=NOW + timedelta(seconds=11))
    assert lease.heartbeat("one", first, ttl_seconds=10, now=NOW + timedelta(seconds=12)) is False


def test_current_generation_can_heartbeat(tmp_path):
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
    generation = lease.acquire("one", ttl_seconds=10, now=NOW)
    assert lease.heartbeat("one", generation, ttl_seconds=20, now=NOW + timedelta(seconds=5)) is True
    assert lease.is_current("one", generation, now=NOW + timedelta(seconds=15)) is True


def test_stale_generation_cannot_release_new_leader(tmp_path):
    lease = ObserverLease(str(tmp_path / "lease.sqlite3"))
    first = lease.acquire("one", ttl_seconds=10, now=NOW)
    second = lease.acquire("two", ttl_seconds=10, now=NOW + timedelta(seconds=11))
    assert lease.release("one", first) is False
    assert lease.is_current("two", second, now=NOW + timedelta(seconds=12)) is True
