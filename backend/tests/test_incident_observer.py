from app.incident_observer import observe_incidents
from app.incident_store import IncidentStore


def healthy_metrics():
    return {
        "oldest_queued_age_seconds": 0,
        "oldest_outbox_pending_age_seconds": 0,
        "jobs_by_status": {"failed": 0},
        "worker_watchdog": {"status": "ok"},
    }


def healthy_telemetry():
    return {
        "windows": {
            "300": {"events": 100, "failure_rate": 0.0},
            "3600": {"events": 1000, "failure_rate": 0.0},
        }
    }


def test_healthy_observation_does_not_create_incident(tmp_path):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    result = observe_incidents(store, healthy_metrics(), healthy_telemetry())
    history, _ = store.read()
    assert result["state"] == "healthy"
    assert result["changed"] is False
    assert history == []


def test_critical_watchdog_opens_incident(tmp_path):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    metrics = healthy_metrics()
    metrics["worker_watchdog"] = {"status": "error"}
    result = observe_incidents(store, metrics, healthy_telemetry())
    history, _ = store.read()
    assert result["state"] == "critical"
    assert result["changed"] is True
    assert history[-1]["status"] == "opened"


def test_repeated_identical_incident_is_deduplicated(tmp_path):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    metrics = healthy_metrics()
    metrics["worker_watchdog"] = {"status": "error"}
    observe_incidents(store, metrics, healthy_telemetry())
    observe_incidents(store, metrics, healthy_telemetry())
    history, _ = store.read()
    assert len({(item["domain"], item["fingerprint"]) for item in history}) == len(history)


def test_healthy_observation_resolves_active_incident(tmp_path):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    metrics = healthy_metrics()
    metrics["worker_watchdog"] = {"status": "error"}
    observe_incidents(store, metrics, healthy_telemetry())
    observe_incidents(store, healthy_metrics(), healthy_telemetry())
    history, _ = store.read()
    assert history[-1]["status"] == "resolved"
