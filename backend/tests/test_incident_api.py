import pytest

from app.incident_api import (
    IncidentApiConflict,
    acknowledge_incident_versioned,
    read_incident_status,
)
from app.incident_store import IncidentStore


def seeded_store(tmp_path):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    _, version = store.read()
    store.write(
        [{
            "domain": "workload",
            "fingerprint": "abc",
            "dedupe_key": "operational:workload:abc",
            "severity": "degraded",
            "status": "opened",
            "opened_at": "2026-09-15T12:00:00+00:00",
            "last_seen_at": "2026-09-15T12:00:00+00:00",
            "acknowledged_at": None,
            "resolved_at": None,
        }],
        expected_version=version,
    )
    return store


def test_read_contract_exposes_active_history_and_version(tmp_path):
    result = read_incident_status(seeded_store(tmp_path))
    assert result["active"][0]["fingerprint"] == "abc"
    assert result["version"] >= 2
    assert result["read_only"] is True


def test_acknowledge_requires_current_version(tmp_path):
    store = seeded_store(tmp_path)
    _, version = store.read()
    result = acknowledge_incident_versioned(store, "abc", expected_version=version)
    assert result["changed"] is True
    saved, new_version = store.read()
    assert saved[0]["status"] == "acknowledged"
    assert new_version == result["version"]


def test_stale_acknowledgement_is_conflict(tmp_path):
    store = seeded_store(tmp_path)
    _, version = store.read()
    acknowledge_incident_versioned(store, "abc", expected_version=version)
    with pytest.raises(IncidentApiConflict):
        acknowledge_incident_versioned(store, "abc", expected_version=version)


def test_unknown_or_non_open_incident_is_noop(tmp_path):
    store = seeded_store(tmp_path)
    _, version = store.read()
    result = acknowledge_incident_versioned(store, "missing", expected_version=version)
    assert result["changed"] is False
    assert result["reason"] == "incident_not_open"
