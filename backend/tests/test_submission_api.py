import pytest
from fastapi import HTTPException

import app.submission_api as submission_api
from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.storage import Storage


def _setup(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            Finding(
                id="f1",
                title="confirmed fixture",
                severity="medium",
                asset="https://example.test",
                summary="bounded fixture",
                status="confirmed",
                discovered_by="scanner",
                validated_by="independent-validator",
            )
        ],
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    artifact = store.put_artifact(campaign.id, "report", b"report", media_type="text/markdown")
    return campaign, artifact


def test_submission_api_requires_approval(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)

    with pytest.raises(HTTPException) as exc:
        submission_api.mark_report_submitted(campaign.id, artifact["id"], "operator", "generic")

    assert exc.value.status_code == 409


def test_approve_then_mark_submitted_is_idempotent(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)

    approved = submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
    submitted = submission_api.mark_report_submitted(campaign.id, artifact["id"], "operator", "generic")
    repeated = submission_api.mark_report_submitted(campaign.id, artifact["id"], "operator", "generic")

    assert approved["state"] == "approved"
    assert submitted["state"] == "submitted"
    assert repeated == submitted


def test_conflicting_submission_metadata_is_rejected(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)
    submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
    submission_api.mark_report_submitted(campaign.id, artifact["id"], "operator", "generic")

    with pytest.raises(HTTPException) as exc:
        submission_api.mark_report_submitted(campaign.id, artifact["id"], "other-operator", "generic")

    assert exc.value.status_code == 409


def test_revocation_reblocks_submission_state(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)
    submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
    submission_api.revoke_report_approval(campaign.id, artifact["id"], "reviewer")

    status = submission_api.get_submission_state(campaign.id, artifact["id"])

    assert status["state"] == "draft"
    assert status["approved"] is False


def test_non_report_artifact_is_rejected(tmp_path, monkeypatch):
    campaign, _artifact = _setup(tmp_path, monkeypatch)
    store = Storage()
    evidence = store.put_artifact(campaign.id, "http_evidence", b"evidence")

    with pytest.raises(HTTPException) as exc:
        submission_api.get_submission_state(campaign.id, evidence["id"])

    assert exc.value.status_code == 409


def test_tampered_report_is_rejected(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)
    store = Storage()
    metadata = store.get_artifact(campaign.id, artifact["id"])
    assert metadata is not None
    (store.artifact_root / metadata["relative_path"]).write_bytes(b"tampered")

    with pytest.raises(HTTPException) as exc:
        submission_api.get_submission_state(campaign.id, artifact["id"])

    assert exc.value.status_code == 409
