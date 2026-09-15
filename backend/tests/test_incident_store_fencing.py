from datetime import datetime, timedelta, timezone

import pytest

from app.incident_store import IncidentFenceConflict, IncidentStore
from app.observer_lease import ObserverLease


def test_current_leader_can_commit(tmp_path):
    path = str(tmp_path / "shared.sqlite3")
    lease = ObserverLease(path)
    store = IncidentStore(path)
    generation = lease.acquire("leader", ttl_seconds=90)
    _, version = store.read()
    new_version = store.write(
        [{"status": "opened"}],
        expected_version=version,
        fence_owner="leader",
        fence_generation=generation,
    )
    assert new_version == version + 1


def test_stale_leader_cannot_commit_after_failover(tmp_path):
    path = str(tmp_path / "shared.sqlite3")
    lease = ObserverLease(path)
    store = IncidentStore(path)
    now = datetime.now(timezone.utc)
    old_generation = lease.acquire("old", ttl_seconds=10, now=now)
    new_generation = lease.acquire("new", ttl_seconds=10, now=now + timedelta(seconds=11))
    assert new_generation > old_generation

    _, version = store.read()
    with pytest.raises(IncidentFenceConflict):
        store.write(
            [{"status": "opened"}],
            expected_version=version,
            fence_owner="old",
            fence_generation=old_generation,
        )


def test_incomplete_fence_fails_closed(tmp_path):
    path = str(tmp_path / "shared.sqlite3")
    ObserverLease(path)
    store = IncidentStore(path)
    _, version = store.read()
    with pytest.raises(IncidentFenceConflict):
        store.write(
            [{"status": "opened"}],
            expected_version=version,
            fence_owner="leader",
        )
