import pytest
from fastapi import HTTPException

import app.hackerone_api as hackerone_api
from app.campaign_audit import append_campaign_event
from app.hackerone_client import HackerOneClientError
from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.report_approval import approval_event_from_storage
from app.storage import Storage


def _setup(tmp_path, monkeypatch, *, confirmed=1, remote=True):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_HACKERONE_API_USERNAME", "researcher")
    monkeypatch.setenv(
        "XBOW_HACKERONE_API_TOKEN",
        "test-token-value-1234567890",
    )

    campaign = Campaign(
        id="h1-submit",
        target=TargetInput(
            name="HackerOne outbound fixture",
            primary_url="https://example.com",
            rules=ProgramRules(
                authorization_reference="H1-OUTBOUND-1",
                allowed_targets=["example.com"],
                max_requests_per_second=1.0,
            ),
        ),
        findings=[
            Finding(
                id=f"f-{index}",
                title=f"Fixture vulnerability {index}",
                severity="medium",
                asset="https://example.com",
                endpoint="https://example.com/profile",
                summary="Reviewed summary.",
                impact="Reviewed impact.",
                reproduction_steps=["Open the affected endpoint.", "Observe the fixture issue."],
                remediation="Apply the reviewed fix.",
                cwe="CWE-200",
                cvss=5.3,
                status="confirmed",
                discovered_by="nuclei",
                validated_by="independent-http-validator",
            )
            for index in range(confirmed)
        ],
    )
    append_campaign_event(
        campaign.events,
        {
            "type": "hackerone_policy_bound",
            "provider": "hackerone",
            "mode": "conservative",
            **(
                {
                    "remote_binding": {
                        "handle": "security",
                        "snapshot_sha256": "a" * 64,
                        "verified": True,
                    }
                }
                if remote
                else {}
            ),
        },
    )

    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    artifact = store.put_artifact(
        campaign.id,
        "report",
        b"# Approved HackerOne report\n\nExact reviewed body.",
        media_type="text/markdown",
    )

    raw, version = store.get_campaign_record(campaign.id)
    current = Campaign.model_validate(raw)
    append_campaign_event(
        current.events,
        approval_event_from_storage(
            current,
            store,
            artifact["id"],
            "reviewer",
            "2026-09-18T20:00:00+02:00",
        ),
    )
    store.save_campaign(current.model_dump(mode="json"), expected_version=version)
    return current, artifact, store


def _payload():
    return hackerone_api.HackerOneReportSubmissionInput(
        actor="operator",
        confirm_submission=True,
    )


def test_hackerone_external_submission_is_disabled_by_default(tmp_path, monkeypatch):
    campaign, artifact, _store = _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("XBOW_ENABLE_HACKERONE_SUBMISSION", raising=False)

    with pytest.raises(HTTPException) as exc:
        hackerone_api.submit_hackerone_report(campaign.id, artifact["id"], _payload())

    assert exc.value.status_code == 409
    assert "disabled" in str(exc.value.detail).lower()


def test_hackerone_external_submission_requires_verified_remote_binding(tmp_path, monkeypatch):
    campaign, artifact, _store = _setup(tmp_path, monkeypatch, remote=False)
    monkeypatch.setenv("XBOW_ENABLE_HACKERONE_SUBMISSION", "true")

    with pytest.raises(HTTPException) as exc:
        hackerone_api.submit_hackerone_report(campaign.id, artifact["id"], _payload())

    assert exc.value.status_code == 409
    assert "remote" in str(exc.value.detail).lower()


def test_hackerone_external_submission_requires_single_confirmed_finding(tmp_path, monkeypatch):
    campaign, artifact, _store = _setup(tmp_path, monkeypatch, confirmed=2)
    monkeypatch.setenv("XBOW_ENABLE_HACKERONE_SUBMISSION", "true")

    with pytest.raises(HTTPException) as exc:
        hackerone_api.submit_hackerone_report(campaign.id, artifact["id"], _payload())

    assert exc.value.status_code == 409
    assert "exactly one" in str(exc.value.detail).lower()


def test_hackerone_external_submission_posts_exact_approved_report_once(tmp_path, monkeypatch):
    campaign, artifact, store = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_HACKERONE_SUBMISSION", "true")
    calls = []

    def post_json(self, path, payload):
        calls.append((path, payload))
        return {"data": {"id": "4242", "type": "report"}}

    monkeypatch.setattr(hackerone_api.HackerOneClient, "post_json", post_json)

    result = hackerone_api.submit_hackerone_report(
        campaign.id,
        artifact["id"],
        _payload(),
    )

    assert result["state"] == "submitted"
    assert result["platform"] == "hackerone"
    assert result["remote_report_id"] == "4242"
    assert len(calls) == 1
    path, outbound = calls[0]
    assert path == "hackers/reports"
    attributes = outbound["data"]["attributes"]
    assert attributes["team_handle"] == "security"
    assert attributes["title"] == "Fixture vulnerability 0"
    assert attributes["vulnerability_information"] == (
        "# Approved HackerOne report\n\nExact reviewed body."
    )
    assert attributes["impact"] == "Reviewed impact."
    assert attributes["severity_rating"] == "medium"

    persisted = store.get_campaign(campaign.id)
    event_types = [event.get("type") for event in persisted["events"]]
    assert "hackerone_submission_attempted" in event_types
    assert "hackerone_report_submitted" in event_types
    assert "report_submitted" in event_types

    repeated = hackerone_api.submit_hackerone_report(
        campaign.id,
        artifact["id"],
        _payload(),
    )
    assert repeated == result
    assert len(calls) == 1


def test_hackerone_timeout_leaves_unresolved_attempt_and_blocks_retry(tmp_path, monkeypatch):
    campaign, artifact, store = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_HACKERONE_SUBMISSION", "true")
    calls = 0

    def fail(self, path, payload):
        nonlocal calls
        calls += 1
        raise HackerOneClientError("HackerOne transport timed out")

    monkeypatch.setattr(hackerone_api.HackerOneClient, "post_json", fail)

    with pytest.raises(HTTPException) as first:
        hackerone_api.submit_hackerone_report(campaign.id, artifact["id"], _payload())
    assert first.value.status_code == 502
    assert "unresolved" in str(first.value.detail).lower()

    persisted = store.get_campaign(campaign.id)
    assert any(
        event.get("type") == "hackerone_submission_attempted"
        for event in persisted["events"]
    )

    with pytest.raises(HTTPException) as second:
        hackerone_api.submit_hackerone_report(campaign.id, artifact["id"], _payload())
    assert second.value.status_code == 409
    assert "unresolved" in str(second.value.detail).lower()
    assert calls == 1
