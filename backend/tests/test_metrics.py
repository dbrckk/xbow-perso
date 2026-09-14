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
    assert result["pending_outbox_total"] == 0
    assert result["pending_outbox_by_kind"] == {}
    assert result["oldest_outbox_pending_age_seconds"] is None
    assert result["contains_outbox_identities"] is False
    rendered = str(result)
    assert "secret.example" not in rendered
    assert "other.example" not in rendered


def test_metrics_route_is_exposed_under_authenticated_api():
    assert "/api/metrics" in app.openapi()["paths"]



def test_operational_metrics_include_recovery_readiness_history():
    class ReadinessStorage(Storage):
        def list_recovery_readiness_snapshots(self, limit=100):
            return [
                {"decision": "BLOCK"},
                {"decision": "READY"},
                {"decision": "REVIEW"},
            ]

    result = build_operational_metrics(Queue(), ReadinessStorage())

    assert result["recovery_readiness"]["supported"] is True
    assert result["recovery_readiness"]["latest_decision"] == "BLOCK"
    assert result["recovery_readiness"]["snapshots"] == 3
    assert result["recovery_readiness"]["by_decision"] == {
        "BLOCK": 1,
        "READY": 1,
        "REVIEW": 1,
    }
    assert result["recovery_readiness"]["transitions"] == 2
    assert result["recovery_readiness"]["ready_to_block_regressions"] == 1



def test_operational_metrics_include_control_plane_health_trend():
    class HealthStorage(Storage):
        def list_control_plane_health_snapshots(self, limit=100):
            return [
                {"score": 68, "state": "BLOCKED"},
                {"score": 82, "state": "DEGRADED"},
                {"score": 95, "state": "HEALTHY"},
            ]

    result = build_operational_metrics(Queue(), HealthStorage())

    health = result["control_plane_health"]
    assert health["supported"] is True
    assert health["latest_score"] == 68
    assert health["previous_score"] == 82
    assert health["delta"] == -14
    assert health["trend"] == "degrading"
    assert health["latest_state"] == "BLOCKED"
    assert health["transitions"] == 2
    assert health["healthy_to_degraded_transitions"] == 1
    assert health["to_blocked_transitions"] == 1
    assert health["persistent_degradation"] is True
