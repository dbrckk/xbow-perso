from datetime import datetime, timedelta, timezone

import pytest

from app.incident_observer import observe_incidents
from app.incident_store import IncidentFenceConflict, IncidentStore
from app.observer_lease import ObserverLease
from app.observer_scheduler import run_scheduled_observation


def critical_metrics():
    return {
        "oldest_queued_age_seconds": 0,
        "oldest_outbox_pending_age_seconds": 0,
        "jobs_by_status": {"failed": 0},
        "worker_watchdog": {"status": "error"},
    }


def telemetry():
    return {
        "windows": {
            "300": {"events": 100, "failure_rate": 0.0},
            "3600": {"events": 1000, "failure_rate": 0.0},
        }
    }


def test_scheduler_passes_owner_and_generation(tmp_path):
    path = str(tmp_path / "shared.sqlite3")
    lease = ObserverLease(path)
    seen = {}

    def observe(owner, generation):
        seen["owner"] = owner
        seen["generation"] = generation
        return {"ok": True}

    result = run_scheduled_observation(lease, "node-a", observe)
    assert result["ran"] is True
    assert seen == {"owner": "node-a", "generation": result["generation"]}


def test_stale_leader_end_to_end_commit_is_rejected(tmp_path):
    path = str(tmp_path / "shared.sqlite3")
    lease = ObserverLease(path)
    store = IncidentStore(path)
    now = datetime.now(timezone.utc)

    generation_a = lease.acquire("node-a", ttl_seconds=10, now=now)
    generation_b = lease.acquire("node-b", ttl_seconds=10, now=now + timedelta(seconds=11))
    assert generation_b > generation_a

    with pytest.raises(IncidentFenceConflict):
        observe_incidents(
            store,
            critical_metrics(),
            telemetry(),
            fence_owner="node-a",
            fence_generation=generation_a,
        )

    history, _ = store.read()
    assert history == []


def test_current_leader_end_to_end_commit_succeeds(tmp_path):
    path = str(tmp_path / "shared.sqlite3")
    lease = ObserverLease(path)
    store = IncidentStore(path)
    generation = lease.acquire("node-b", ttl_seconds=90)

    result = observe_incidents(
        store,
        critical_metrics(),
        telemetry(),
        fence_owner="node-b",
        fence_generation=generation,
    )
    history, _ = store.read()
    assert result["changed"] is True
    assert history[-1]["status"] == "opened"
