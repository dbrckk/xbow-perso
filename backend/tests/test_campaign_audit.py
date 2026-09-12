import copy

from app.campaign_audit import append_campaign_event, verify_campaign_event_chain


def test_campaign_event_chain_detects_tampering(monkeypatch):
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    events = []
    append_campaign_event(events, {"type": "campaign_created", "at": "t1"})
    append_campaign_event(events, {"type": "campaign_started", "at": "t2", "job_id": "j1"})
    assert verify_campaign_event_chain(events)["valid"] is True

    tampered = copy.deepcopy(events)
    tampered[1]["job_id"] = "evil"
    result = verify_campaign_event_chain(tampered)
    assert result["valid"] is False
    assert result["reason"] == "campaign event hash mismatch"


def test_campaign_event_chain_detects_reordering(monkeypatch):
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    events = []
    append_campaign_event(events, {"type": "a", "at": "t1"})
    append_campaign_event(events, {"type": "b", "at": "t2"})
    events.reverse()
    assert verify_campaign_event_chain(events)["valid"] is False


def test_campaign_event_chain_supports_hmac(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "audit-secret")
    events = []
    append_campaign_event(events, {"type": "campaign_created", "at": "t1"})
    assert events[0]["event_signature_alg"] == "hmac-sha256"
    assert verify_campaign_event_chain(events)["valid"] is True
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "wrong")
    assert verify_campaign_event_chain(events)["valid"] is False


def test_campaign_event_chain_reports_legacy_prefix(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    events = [{"type": "legacy", "at": "old"}]
    append_campaign_event(events, {"type": "new", "at": "now"})
    result = verify_campaign_event_chain(events)
    assert result["valid"] is True
    assert result["legacy_unsealed"] == 1
    assert result["checked"] == 1
