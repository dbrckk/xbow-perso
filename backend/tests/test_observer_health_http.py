from fastapi.testclient import TestClient

from app import main
from app.observer_runtime import observer_runtime


TOKEN = "t" * 32


def test_observer_health_route_uses_shared_runtime(monkeypatch):
    monkeypatch.setenv("XBOW_API_TOKEN", TOKEN)
    runtime = observer_runtime()
    before = runtime.snapshot()["deadline_exceeded_count"]
    runtime.health.note_deadline_exceeded()

    response = TestClient(main.app).get(
        "/api/observer/health",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["deadline_exceeded_count"] == before + 1
    assert payload["contains_targets"] is False
    assert payload["contains_secrets"] is False
