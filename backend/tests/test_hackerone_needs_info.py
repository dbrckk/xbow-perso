import pytest
from fastapi import HTTPException

import app.hackerone_api as hackerone_api
from app.campaign_audit import append_campaign_event
from app.hackerone_report_tracking import project_needs_more_info_request
from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.storage import Storage


def _report_document(*, activity_type="activity-bug-needs-more-info", internal=False):
    return {
        "data": {
            "id": "4242",
            "type": "report",
            "attributes": {
                "state": "needs-more-info",
                "created_at": "2026-09-18T18:00:00Z",
                "last_activity_at": "2026-09-18T20:30:00Z",
            },
            "relationships": {
                "activities": {
                    "data": [
                        {
                            "id": "9001",
                            "type": activity_type,
                            "attributes": {
                                "report_id": "4242",
                                "message": "Can you provide the exact request and response headers?",
                                "internal": internal,
                                "created_at": "2026-09-18T20:30:00Z",
                                "updated_at": "2026-09-18T20:31:00Z",
                            },
                            "relationships": {
                                "actor": {
                                    "data": {
                                        "id": "sensitive-user-id",
                                        "type": "user",
                                        "attributes": {
                                            "username": "triager",
                                            "name": "Sensitive Person",
                                        },
                                    }
                                }
                            },
                        }
                    ]
                }
            },
        }
    }


def test_needs_more_info_projection_keeps_only_public_bounded_fields():
    result = project_needs_more_info_request(
        _report_document(),
        expected_report_id="4242",
    )

    assert result == {
        "activity_id": "9001",
        "activity_type": "activity-bug-needs-more-info",
        "message": "Can you provide the exact request and response headers?",
        "created_at": "2026-09-18T20:30:00Z",
        "updated_at": "2026-09-18T20:31:00Z",
        "internal": False,
    }
    assert "actor" not in result
    assert "relationships" not in result


def test_needs_more_info_projection_ignores_internal_or_unrelated_activity():
    assert (
        project_needs_more_info_request(
            _report_document(internal=True),
            expected_report_id="4242",
        )
        is None
    )
    assert (
        project_needs_more_info_request(
            _report_document(activity_type="activity-comment"),
            expected_report_id="4242",
        )
        is None
    )


def _setup_campaign(tmp_path, monkeypatch):
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
        id="h1-nmi",
        target=TargetInput(
            name="NMI fixture",
            primary_url="https://example.com",
            rules=ProgramRules(
                authorization_reference="H1-NMI-1",
                allowed_targets=["example.com"],
            ),
        ),
        findings=[
            Finding(
                id="f-1",
                title="Validated fixture issue",
                severity="medium",
                asset="https://example.com",
                endpoint="https://example.com/profile",
                summary="Validated summary.",
                impact="Validated impact.",
                reproduction_steps=[
                    "Send the recorded request.",
                    "Observe the validated response condition.",
                ],
                evidence=["Request/response artifact stored locally."],
                remediation="Apply the reviewed fix.",
                status="confirmed",
                discovered_by="nuclei",
                validated_by="independent-http-validator",
            )
        ],
    )
    append_campaign_event(
        campaign.events,
        {
            "type": "hackerone_report_submitted",
            "artifact_id": "report-1",
            "remote_report_id": "4242",
            "team_handle": "security",
            "actor": "operator",
            "at": "2026-09-18T20:00:00+02:00",
        },
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    return campaign


def test_remote_status_includes_public_needs_more_info_request(tmp_path, monkeypatch):
    campaign = _setup_campaign(tmp_path, monkeypatch)
    monkeypatch.setattr(
        hackerone_api.HackerOneClient,
        "get_json",
        lambda self, path, query=None: _report_document(),
    )

    result = hackerone_api.get_hackerone_remote_report_status(
        campaign.id,
        "report-1",
    )

    assert result["state"] == "needs-more-info"
    assert result["needs_more_info"]["activity_id"] == "9001"
    assert "triager" not in str(result)


def test_needs_more_info_draft_is_local_and_contains_no_send_action(tmp_path, monkeypatch):
    campaign = _setup_campaign(tmp_path, monkeypatch)
    monkeypatch.setattr(
        hackerone_api.HackerOneClient,
        "get_json",
        lambda self, path, query=None: _report_document(),
    )

    result = hackerone_api.get_hackerone_needs_more_info_draft(
        campaign.id,
        "report-1",
    )

    assert result["provider"] == "hackerone"
    assert result["remote_report_id"] == "4242"
    assert result["activity_id"] == "9001"
    assert result["requires_human_review"] is True
    assert result["send_supported"] is False
    draft = result["draft_markdown"]
    assert "Can you provide the exact request and response headers?" in draft
    assert "Validated fixture issue" in draft
    assert "https://example.com/profile" in draft
    assert "Send the recorded request." in draft
    assert "Human review required" in draft
    assert "Sensitive Person" not in draft


def test_needs_more_info_draft_requires_active_public_request(tmp_path, monkeypatch):
    campaign = _setup_campaign(tmp_path, monkeypatch)
    document = _report_document(activity_type="activity-comment")
    document["data"]["attributes"]["state"] = "triaged"
    monkeypatch.setattr(
        hackerone_api.HackerOneClient,
        "get_json",
        lambda self, path, query=None: document,
    )

    with pytest.raises(HTTPException) as exc:
        hackerone_api.get_hackerone_needs_more_info_draft(
            campaign.id,
            "report-1",
        )

    assert exc.value.status_code == 409
