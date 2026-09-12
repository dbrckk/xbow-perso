from app.main import app
from app.metrics import build_operational_metrics


class Queue:
    def stats(self):
        return {
            "total": 7,
            "storage": "redis",
            "by_status": {
                "running": 1,
                "queued": 2,
                "completed": 4,
            },
        }


class Storage:
    def list_campaigns(self):
        return [
            {"id": "c1", "state": "ready", "target": {"primary_url": "https://secret.example"}},
            {"id": "c2", "state": "running", "target": {"primary_url": "https://other.example"}},
            {"id": "c3", "state": "running", "target": {"primary_url": "https://third.example"}},
        ]


def test_operational_metrics_are_aggregate_only():
    result = build_operational_metrics(Queue(), Storage())

    assert result["campaigns_total"] == 3
    assert result["campaigns_by_state"] == {"ready": 1, "running": 2}
    assert result["jobs_total"] == 7
    assert result["jobs_by_status"]["completed"] == 4
    assert result["queue_storage"] == "redis"
    assert result["read_only"] is True
    assert result["contains_targets"] is False
    assert result["contains_payloads"] is False
    assert result["contains_secrets"] is False
    rendered = str(result)
    assert "secret.example" not in rendered
    assert "other.example" not in rendered


def test_metrics_route_is_exposed_under_authenticated_api():
    assert "/api/metrics" in app.openapi()["paths"]
