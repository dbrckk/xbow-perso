from app.main import app
from app.operations_dashboard import build_operations_dashboard


class Queue:
    def stats(self):
        return {
            "total": 3,
            "storage": "sqlite",
            "by_status": {"completed": 2, "failed": 1},
        }

    def campaign_transition_audit(self, campaign_id):
        return {
            "valid": True,
            "events": 2,
            "invalid_jobs": [],
        }


class Storage:
    def __init__(self, decisions=None):
        self.decisions = decisions or []

    def list_campaigns(self):
        return [
            {"id": "c1", "state": "running", "events": []},
            {"id": "c2", "state": "completed", "events": []},
        ]

    def list_recovery_readiness_snapshots(self, limit=100):
        return [
            {"decision": decision, "created_at": f"2026-09-14T12:0{i}:00+00:00", "fingerprint": str(i)}
            for i, decision in enumerate(reversed(self.decisions))
        ][:limit]


def test_operations_dashboard_is_aggregate_and_read_only():
    result = build_operations_dashboard(Queue(), Storage(["READY"]))

    assert result["health"] == "DEGRADED"
    assert result["summary"]["campaigns_total"] == 2
    assert result["summary"]["failed_jobs"] == 1
    assert result["queue_integrity"]["audit_valid"] is True
    assert result["read_only"] is True
    assert result["aggregate_only"] is True
    assert result["automatic_worker_start"] is False
    assert result["automatic_mutation"] is False
    assert result["contains_targets"] is False
    assert result["contains_payloads"] is False
    assert result["contains_secrets"] is False


def test_operations_dashboard_blocks_on_recovery_block():
    result = build_operations_dashboard(Queue(), Storage(["BLOCK"]))

    assert result["health"] == "BLOCKED"
    assert "recovery_readiness_block" in result["blocked_reasons"]


def test_operations_dashboard_tracks_ready_to_block():
    result = build_operations_dashboard(Queue(), Storage(["READY", "BLOCK"]))

    assert result["health"] == "BLOCKED"
    assert result["recovery"]["ready_to_block_regressions"] == 1
    assert result["recovery"]["recent_transitions"][0]["from"] == "READY"
    assert result["recovery"]["recent_transitions"][0]["to"] == "BLOCK"


def test_operations_dashboard_route_is_exposed():
    assert "/api/dashboard/operations" in app.openapi()["paths"]
