import pytest

from app.incident_store import IncidentStore, IncidentStoreConflict


def test_incident_store_round_trip(tmp_path):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    history, version = store.read()
    assert history == []
    new_version = store.write([{"fingerprint": "abc", "status": "opened"}], expected_version=version)
    saved, saved_version = store.read()
    assert saved[0]["fingerprint"] == "abc"
    assert new_version == saved_version


def test_incident_store_rejects_stale_version(tmp_path):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    _, version = store.read()
    store.write([{"fingerprint": "one"}], expected_version=version)
    with pytest.raises(IncidentStoreConflict):
        store.write([{"fingerprint": "two"}], expected_version=version)


def test_incident_store_instances_share_state(tmp_path):
    path = str(tmp_path / "incidents.sqlite3")
    first = IncidentStore(path)
    second = IncidentStore(path)
    _, version = first.read()
    first.write([{"status": "opened"}], expected_version=version)
    history, _ = second.read()
    assert history == [{"status": "opened"}]
