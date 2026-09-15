from app.incident_api import read_incident_status
from app.incident_observer import observe_incidents
from app.incident_store import IncidentStore


def telemetry():
    return {
        "windows": {
            "300": {"events": 100, "failure_rate": 0.0},
            "3600": {"events": 1000, "failure_rate": 0.0},
        }
    }


def metrics(watchdog="ok", failed=0):
    return {
        "oldest_queued_age_seconds": 0,
        "oldest_outbox_pending_age_seconds": 0,
        "jobs_by_status": {"failed": failed},
        "worker_watchdog": {"status": watchdog},
    }


def test_observer_persists_independent_domain_incidents(tmp_path, monkeypatch):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    import app.incident_observer as observer

    monkeypatch.setattr(
        observer,
        "build_observer_slo",
        lambda value: {"state": "degraded", "reasons": ["test"]},
    )
    observe_incidents(store, metrics(watchdog="error"), telemetry())
    status = read_incident_status(store)

    assert status["active_by_domain"]["control_plane"] is not None
    assert status["active_by_domain"]["observability"] is not None
    assert len(status["active"]) >= 2


def test_domain_recovery_does_not_close_other_active_incident(tmp_path, monkeypatch):
    store = IncidentStore(str(tmp_path / "incidents.sqlite3"))
    import app.incident_observer as observer

    monkeypatch.setattr(
        observer,
        "build_observer_slo",
        lambda value: {"state": "degraded", "reasons": ["test"]},
    )
    observe_incidents(store, metrics(watchdog="error"), telemetry())
    observe_incidents(store, metrics(watchdog="ok"), telemetry())
    status = read_incident_status(store)

    assert status["active_by_domain"]["control_plane"] is None
    assert status["active_by_domain"]["observability"] is not None
