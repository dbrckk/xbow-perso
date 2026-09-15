from fastapi.testclient import TestClient

from app import main


TOKEN = "t" * 32


def client(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_API_TOKEN", TOKEN)
    monkeypatch.delenv("XBOW_SECRET_VAULT_PATH", raising=False)
    monkeypatch.delenv("XBOW_TOTP_SECRET", raising=False)
    db_path = str(tmp_path / "incidents.sqlite3")

    class Store:
        def __init__(self):
            self.db_path = db_path

    monkeypatch.setattr(main, "storage", lambda: Store())
    return TestClient(main.app)


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_incident_read_requires_authentication(monkeypatch, tmp_path):
    response = client(monkeypatch, tmp_path).get("/api/incidents")
    assert response.status_code == 401


def test_incident_read_returns_versioned_state(monkeypatch, tmp_path):
    response = client(monkeypatch, tmp_path).get("/api/incidents", headers=auth())
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] >= 1
    assert payload["history"] == []
    assert payload["active"] == []


def test_acknowledge_unknown_incident_is_safe_noop(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    current = c.get("/api/incidents", headers=auth()).json()
    response = c.post(
        "/api/incidents/acknowledge",
        headers=auth(),
        json={"fingerprint": "a" * 24, "expected_version": current["version"]},
    )
    assert response.status_code == 200
    assert response.json()["changed"] is False


def test_acknowledge_rejects_stale_version(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    store = main.incident_store()
    _, version = store.read()
    store.write([{
        "fingerprint": "a" * 24,
        "dedupe_key": "operational:" + "a" * 24,
        "severity": "degraded",
        "status": "opened",
        "opened_at": "2026-09-15T12:00:00+00:00",
        "last_seen_at": "2026-09-15T12:00:00+00:00",
        "acknowledged_at": None,
        "resolved_at": None,
    }], expected_version=version)

    response = c.post(
        "/api/incidents/acknowledge",
        headers=auth(),
        json={"fingerprint": "a" * 24, "expected_version": version},
    )
    assert response.status_code == 409
