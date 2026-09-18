import pytest
from fastapi import HTTPException

import app.hackerone_api as hackerone_api
from app.campaign_audit import append_campaign_event
from app.hackerone_client import HackerOneClientError
from app.main import Campaign, ProgramRules, TargetInput
from app.storage import Storage


def _campaign_with_remote_report(tmp_path, monkeypatch, *, remote_report_id="4242"):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_HACKERONE_API_USERNAME", "researcher")
    monkeypatch.setenv(
        "XBOW_HACKERONE_API_TOKEN",
        "test-token-value-1234567890",
    )

    campaign = Campaign(
        id="h1-track",
        target=TargetInput(
            name="tracking fixture",
            primary_url="https://example.com",
            rules=ProgramRules(
                authorization_reference="H1-TRACK-1",
                allowed_targets=["example.com"],
            ),
        ),
    )
    append_campaign_event(
        campaign.events,
        {
            "type": "hackerone_report_submitted",
            "artifact_id": "report-1",
            "artifact_sha256": "a" * 64,
            "request_id": "request-1",
            "remote_report_id": remote_report_id,
            "team_handle": "security",
            "actor": "operator",
            "at": "2026-09-18T20:00:00+02:00",
        },
    )
    Storage(db, artifacts).save_campaign(
        campaign.model_dump(mode="json"),
        expected_version=0,
    )
    return campaign


def test_remote_report_status_projects_safe_operational_fields(tmp_path, monkeypatch):
    campaign = _campaign_with_remote_report(tmp_path, monkeypatch)
    calls = []

    def get_json(self, path, query=None):
        calls.append((path, query))
        return {
            "data": {
                "id": "4242",
                "type": "report",
                "attributes": {
                    "title": "Sensitive title",
                    "state": "triaged",
                    "created_at": "2026-09-18T18:00:00Z",
                    "triaged_at": "2026-09-18T19:00:00Z",
                    "closed_at": None,
                    "last_program_activity_at": "2026-09-18T19:30:00Z",
                    "last_reporter_activity_at": "2026-09-18T18:30:00Z",
                    "last_activity_at": "2026-09-18T19:30:00Z",
                    "vulnerability_information": "must never be returned",
                },
                "relationships": {
                    "reporter": {
                        "data": {
                            "type": "user",
                            "id": "secret-user-id",
                        }
                    }
                },
            }
        }

    monkeypatch.setattr(hackerone_api.HackerOneClient, "get_json", get_json)

    result = hackerone_api.get_hackerone_remote_report_status(
        campaign.id,
        "report-1",
    )

    assert calls == [("hackers/reports/4242", None)]
    assert result == {
        "provider": "hackerone",
        "artifact_id": "report-1",
        "remote_report_id": "4242",
        "team_handle": "security",
        "state": "triaged",
        "created_at": "2026-09-18T18:00:00Z",
        "triaged_at": "2026-09-18T19:00:00Z",
        "closed_at": None,
        "last_program_activity_at": "2026-09-18T19:30:00Z",
        "last_reporter_activity_at": "2026-09-18T18:30:00Z",
        "last_activity_at": "2026-09-18T19:30:00Z",
        "read_only": True,
    }
    assert "vulnerability_information" not in result
    assert "relationships" not in result
    assert "title" not in result


def test_remote_report_status_requires_recorded_hackerone_submission(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="h1-unsubmitted",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.com",
            rules=ProgramRules(
                authorization_reference="AUTH",
                allowed_targets=["example.com"],
            ),
        ),
    )
    Storage(db, artifacts).save_campaign(
        campaign.model_dump(mode="json"),
        expected_version=0,
    )

    with pytest.raises(HTTPException) as exc:
        hackerone_api.get_hackerone_remote_report_status(
            campaign.id,
            "report-1",
        )

    assert exc.value.status_code == 409


def test_remote_report_status_rejects_mismatched_or_invalid_upstream_payload(
    tmp_path,
    monkeypatch,
):
    campaign = _campaign_with_remote_report(tmp_path, monkeypatch)

    def get_json(self, path, query=None):
        return {
            "data": {
                "id": "9999",
                "type": "report",
                "attributes": {"state": "new"},
            }
        }

    monkeypatch.setattr(hackerone_api.HackerOneClient, "get_json", get_json)

    with pytest.raises(HTTPException) as exc:
        hackerone_api.get_hackerone_remote_report_status(
            campaign.id,
            "report-1",
        )

    assert exc.value.status_code == 502


def test_remote_report_status_maps_upstream_unavailability(tmp_path, monkeypatch):
    campaign = _campaign_with_remote_report(tmp_path, monkeypatch)

    def get_json(self, path, query=None):
        raise HackerOneClientError(
            "HackerOne returned HTTP 429",
            status_code=429,
        )

    monkeypatch.setattr(hackerone_api.HackerOneClient, "get_json", get_json)

    with pytest.raises(HTTPException) as exc:
        hackerone_api.get_hackerone_remote_report_status(
            campaign.id,
            "report-1",
        )

    assert exc.value.status_code == 503
