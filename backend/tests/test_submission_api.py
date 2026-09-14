import pytest
from fastapi import HTTPException

import app.submission_api as submission_api
from app.campaign_audit import verify_campaign_event_chain
from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.observation_graph import Observation
from app.storage import Storage


def _setup(tmp_path, monkeypatch, *, report_ready=True):
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
                impact="bounded impact",
                remediation="apply bounded remediation",
                reproduction_steps=["observe bounded fixture"],
                cwe="CWE-200",
                cvss=5.3,
                status="confirmed",
                discovered_by="scanner",
                validated_by="independent-validator",
            )
        ],
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    if report_ready:
        store.put_observation(
            campaign.id,
            Observation("asset:a", "asset", "example.test", "recon").to_dict(),
        )
        store.put_observation(
            campaign.id,
            Observation(
                "finding:f1",
                "finding",
                "f1",
                "scanner",
                parent_ids=("asset:a",),
            ).to_dict(),
        )
        store.put_observation(
            campaign.id,
            Observation(
                "validation:v1",
                "validation",
                "observed",
                "independent-validator",
                parent_ids=("finding:f1",),
            ).to_dict(),
        )
        store.put_observation(
            campaign.id,
            Observation(
                "evidence:e1",
                "evidence",
                "artifact-reference",
                "independent-validator",
                parent_ids=("validation:v1",),
                metadata={
                    "artifact_id": "validation-artifact-f1",
                    "artifact_sha256": "b" * 64,
                },
            ).to_dict(),
        )
    artifact = store.put_artifact(campaign.id, "report", b"report", media_type="text/markdown")
    return campaign, artifact


def test_submission_routes_are_mounted():
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/campaigns/{campaign_id}/reports/submission-states",
        "/api/campaigns/{campaign_id}/reports/{artifact_id}/submission-state",
        "/api/campaigns/{campaign_id}/reports/{artifact_id}/submission-audit",
        "/api/campaigns/{campaign_id}/reports/{artifact_id}/approve",
        "/api/campaigns/{campaign_id}/reports/{artifact_id}/revoke-approval",
        "/api/campaigns/{campaign_id}/reports/{artifact_id}/mark-submitted",
    }
    assert expected <= paths


def test_campaign_submission_overview_counts_states(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)
    before = submission_api.list_submission_states(campaign.id)
    submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
    after = submission_api.list_submission_states(campaign.id)

    assert before["total"] == 1
    assert before["counts"] == {"draft": 1, "review_required": 0, "approved": 0, "submitted": 0}
    assert after["counts"] == {"draft": 0, "review_required": 0, "approved": 1, "submitted": 0}


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

    assert status["state"] == "review_required"
    assert status["approved"] is False


def test_reapproval_requires_new_manual_submission(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)
    submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
    submission_api.mark_report_submitted(campaign.id, artifact["id"], "operator", "generic")
    submission_api.revoke_report_approval(campaign.id, artifact["id"], "reviewer")
    reapproved = submission_api.approve_report(campaign.id, artifact["id"], "reviewer")

    assert reapproved["state"] == "approved"
    assert reapproved["submitted_at"] is None

    resubmitted = submission_api.mark_report_submitted(
        campaign.id,
        artifact["id"],
        "operator-2",
        "hackerone",
    )
    assert resubmitted["state"] == "submitted"
    assert resubmitted["submitted_by"] == "operator-2"
    assert resubmitted["platform"] == "hackerone"


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


def test_report_approval_rejects_confirmed_finding_without_ready_evidence(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch, report_ready=False)

    with pytest.raises(HTTPException) as exc:
        submission_api.approve_report(campaign.id, artifact["id"], "reviewer")

    assert exc.value.status_code == 400
    assert "report-ready" in str(exc.value.detail)



def test_submission_mutations_preserve_campaign_audit_chain(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)

    submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
    submission_api.mark_report_submitted(
        campaign.id,
        artifact["id"],
        "operator",
        "generic",
    )
    submission_api.revoke_report_approval(
        campaign.id,
        artifact["id"],
        "reviewer",
    )

    persisted = Storage().get_campaign(campaign.id)
    verification = verify_campaign_event_chain(persisted["events"])

    assert verification["valid"] is True
    assert verification["legacy_unsealed"] == 0
    assert [
        event["type"]
        for event in persisted["events"]
        if event["type"] in {
            "report_approved",
            "report_submitted",
            "report_approval_revoked",
        }
    ] == [
        "report_approved",
        "report_submitted",
        "report_approval_revoked",
    ]



def test_provenance_change_after_approval_makes_approval_stale(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)

    approved = submission_api.approve_report(
        campaign.id,
        artifact["id"],
        "reviewer",
    )
    assert approved["state"] == "approved"
    assert approved["stale"] is False

    store = Storage()
    store.put_observation(
        campaign.id,
        Observation(
            "evidence:e2",
            "evidence",
            "artifact-reference",
            "independent-validator",
            parent_ids=("validation:v1",),
            metadata={
                "artifact_id": "validation-artifact-f1-secondary",
                "artifact_sha256": "c" * 64,
            },
        ).to_dict(),
    )

    status = submission_api.get_submission_state(
        campaign.id,
        artifact["id"],
    )

    assert status["state"] == "review_required"
    assert status["approved"] is False
    assert status["stale"] is True



def test_submission_audit_accepts_valid_approval_and_submission(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)
    submission_api.approve_report(campaign.id, artifact["id"], "reviewer")
    submission_api.mark_report_submitted(
        campaign.id,
        artifact["id"],
        "operator",
        "generic",
    )

    audit = submission_api.get_submission_audit(
        campaign.id,
        artifact["id"],
    )

    assert audit["valid"] is True
    assert audit["submissions"] == 1
    assert audit["approval_active"] is True
    assert audit["issues"] == []
    assert audit["latest_approval_provenance_fingerprint"]


def test_submission_audit_detects_submission_without_approval(tmp_path, monkeypatch):
    campaign, artifact = _setup(tmp_path, monkeypatch)
    store = Storage()
    persisted = store.get_campaign(campaign.id)
    persisted["events"].append(
        {
            "type": "report_submitted",
            "artifact_id": artifact["id"],
            "actor": "operator",
            "platform": "generic",
            "at": "2026-09-14T18:30:00Z",
        }
    )
    store.save_campaign(persisted, expected_version=1)

    audit = submission_api.get_submission_audit(
        campaign.id,
        artifact["id"],
    )

    assert audit["valid"] is False
    assert "submission_without_active_approval" in audit["issues"]
