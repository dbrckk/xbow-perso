import copy

from app.campaign_audit import append_campaign_event
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
    assert result["invalid_campaign_audit_chains"] == 0
    assert result["campaigns_with_legacy_audit_events"] == 0
    assert result["legacy_audit_events_total"] == 0
    rendered = str(result)
    assert "secret.example" not in rendered
    assert "other.example" not in rendered


def test_metrics_route_is_exposed_under_authenticated_api():
    assert "/api/metrics" in app.openapi()["paths"]



class AuditStorage:
    def list_campaigns(self):
        valid = []
        append_campaign_event(
            valid,
            {"type": "campaign_created", "at": "t1"},
        )
        append_campaign_event(
            valid,
            {"type": "campaign_started", "at": "t2", "job_id": "j1"},
        )
        invalid = copy.deepcopy(valid)
        invalid[1]["job_id"] = "tampered"
        legacy = [{"type": "legacy_event", "at": "old"}]
        return [
            {"id": "valid", "state": "running", "events": valid},
            {"id": "invalid", "state": "running", "events": invalid},
            {"id": "legacy", "state": "ready", "events": legacy},
        ]


def test_metrics_distinguish_invalid_and_legacy_audit_chains(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)

    result = build_operational_metrics(Queue(), AuditStorage())

    assert result["invalid_campaign_audit_chains"] == 1
    assert result["campaigns_with_legacy_audit_events"] == 1
    assert result["legacy_audit_events_total"] == 1
    assert "tampered" not in str(result)
    assert "legacy_event" not in str(result)
