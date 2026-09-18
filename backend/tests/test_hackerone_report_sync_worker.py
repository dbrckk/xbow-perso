import pytest

from app.campaign_audit import append_campaign_event
from app.hackerone_report_sync_worker import (
    HackerOneReportSyncError,
    _require_enabled,
    sync_once,
)
from app.main import Campaign, ProgramRules, TargetInput
from app.storage import Storage


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, path, query=None):
        self.calls.append((path, query))
        if not self.responses:
            raise AssertionError("unexpected HackerOne request")
        return self.responses.pop(0)


def _setup(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_ENABLE_HACKERONE_REPORT_SYNC", "true")
    monkeypatch.setenv("XBOW_HACKERONE_REPORT_SYNC_MAX_CAMPAIGNS", "10")

    campaign = Campaign(
        id="h1-sync",
        target=TargetInput(
            name="sync fixture",
            primary_url="https://example.com",
            rules=ProgramRules(
                authorization_reference="H1-SYNC-1",
                allowed_targets=["example.com"],
            ),
        ),
    )
    append_campaign_event(
        campaign.events,
        {
            "type": "hackerone_report_submitted",
            "artifact_id": "artifact-1",
            "artifact_sha256": "a" * 64,
            "request_id": "request-1",
            "remote_report_id": "4242",
            "team_handle": "security",
            "actor": "operator",
            "at": "2026-09-18T20:00:00+02:00",
        },
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    return store


def _report(state, *, last_activity_at):
    return {
        "data": {
            "id": "4242",
            "type": "report",
            "attributes": {
                "state": state,
                "created_at": "2026-09-18T18:00:00Z",
                "triaged_at": (
                    "2026-09-18T19:00:00Z" if state != "new" else None
                ),
                "closed_at": (
                    "2026-09-18T21:00:00Z" if state == "resolved" else None
                ),
                "last_program_activity_at": last_activity_at,
                "last_reporter_activity_at": "2026-09-18T18:30:00Z",
                "last_activity_at": last_activity_at,
                "vulnerability_information": "must not be persisted",
            },
        }
    }


def test_sync_worker_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_HACKERONE_REPORT_SYNC", raising=False)

    with pytest.raises(HackerOneReportSyncError, match="disabled"):
        _require_enabled()


def test_sync_records_first_remote_status_snapshot(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    client = _Client(
        [_report("new", last_activity_at="2026-09-18T18:30:00Z")]
    )

    stats = sync_once(store, client)

    assert stats == {
        "campaigns_checked": 1,
        "reports_checked": 1,
        "changes_recorded": 1,
        "errors": 0,
    }
    persisted = store.get_campaign("h1-sync")
    events = [
        event
        for event in persisted["events"]
        if event.get("type") == "hackerone_report_status_synced"
    ]
    assert len(events) == 1
    assert events[0]["state"] == "new"
    assert events[0]["remote_report_id"] == "4242"
    assert "vulnerability_information" not in events[0]


def test_sync_does_not_duplicate_unchanged_snapshot(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    response = _report("triaged", last_activity_at="2026-09-18T19:30:00Z")

    first = sync_once(store, _Client([response]))
    second = sync_once(store, _Client([response]))

    assert first["changes_recorded"] == 1
    assert second["changes_recorded"] == 0
    persisted = store.get_campaign("h1-sync")
    events = [
        event
        for event in persisted["events"]
        if event.get("type") == "hackerone_report_status_synced"
    ]
    assert len(events) == 1


def test_sync_records_state_transition_history(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)

    sync_once(
        store,
        _Client([_report("triaged", last_activity_at="2026-09-18T19:30:00Z")]),
    )
    stats = sync_once(
        store,
        _Client([_report("resolved", last_activity_at="2026-09-18T21:00:00Z")]),
    )

    assert stats["changes_recorded"] == 1
    persisted = store.get_campaign("h1-sync")
    events = [
        event
        for event in persisted["events"]
        if event.get("type") == "hackerone_report_status_synced"
    ]
    assert [event["state"] for event in events] == ["triaged", "resolved"]
    assert events[-1]["closed_at"] == "2026-09-18T21:00:00Z"


def test_sync_is_bounded_to_recent_campaign_limit(tmp_path, monkeypatch):
    store = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("XBOW_HACKERONE_REPORT_SYNC_MAX_CAMPAIGNS", "1")

    older = Campaign(
        id="older",
        target=TargetInput(
            name="older fixture",
            primary_url="https://older.example.com",
            rules=ProgramRules(
                authorization_reference="H1-SYNC-2",
                allowed_targets=["older.example.com"],
            ),
        ),
    )
    append_campaign_event(
        older.events,
        {
            "type": "hackerone_report_submitted",
            "artifact_id": "artifact-old",
            "remote_report_id": "9999",
            "team_handle": "security",
            "actor": "operator",
            "at": "2026-09-18T19:00:00+02:00",
        },
    )
    store.save_campaign(older.model_dump(mode="json"), expected_version=0)

    client = _Client([_report("new", last_activity_at="2026-09-18T18:30:00Z")])
    stats = sync_once(store, client)

    assert stats["campaigns_checked"] == 1
    assert stats["reports_checked"] == 1
    assert len(client.calls) == 1
