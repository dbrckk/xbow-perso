import pytest
from fastapi import HTTPException

from app import main
from app.hackerone_api import HackerOneCampaignAdmissionInput, admit_hackerone_campaign
from app.job_provenance import attach_job_provenance, verify_job_provenance
from app.jobqueue import JobQueue
from app.storage import Storage


def _admission_payload():
    return HackerOneCampaignAdmissionInput(
        document={
            "data": [
                {
                    "type": "structured-scope",
                    "attributes": {
                        "asset_identifier": "example.com",
                        "asset_type": "Domain",
                        "eligible_for_submission": True,
                    },
                }
            ]
        },
        policy={
            "authorization_reference": "H1-PROGRAM-42",
            "policy_version": "2026-09-15",
            "reviewed_at": "2026-09-15T20:00:00+02:00",
            "reviewed_by": "human-reviewer",
            "safe_harbor_confirmed": True,
            "automated_scanning": True,
            "max_requests_per_second": 1.25,
            "test_account_required": False,
            "test_account_constraints": "",
            "additional_restrictions": [],
            "program_notes": "Conservative fixture.",
        },
        target={
            "name": "HackerOne fixture",
            "primary_url": "https://example.com",
        },
    )


def _admitted_campaign(tmp_path, monkeypatch):
    db = str(tmp_path / "campaigns.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    admitted = admit_hackerone_campaign(_admission_payload())
    return admitted, main.Campaign.model_validate(admitted["campaign"])


def test_hackerone_start_rejects_policy_drift_before_enqueue(tmp_path, monkeypatch):
    db = str(tmp_path / "campaigns.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    queue_db = str(tmp_path / "jobs.sqlite3")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    admitted = admit_hackerone_campaign(_admission_payload())
    campaign_id = admitted["campaign"]["id"]

    store = Storage(db, artifacts)
    document, version = store.get_campaign_record(campaign_id)
    document["target"]["rules"]["max_requests_per_second"] = 2.0
    store.save_campaign(document, expected_version=version)

    jobs = JobQueue(queue_db)
    monkeypatch.setattr(main, "queue", lambda: jobs)

    with pytest.raises(HTTPException) as exc:
        main.start_campaign(campaign_id)

    assert exc.value.status_code == 409
    assert exc.value.detail["message"] == "HackerOne policy binding invalid"
    assert "campaign_policy_fingerprint_mismatch" in exc.value.detail["reasons"]
    assert jobs.stats()["total"] == 0


def test_hackerone_binding_is_embedded_in_job_provenance(tmp_path, monkeypatch):
    admitted, campaign = _admitted_campaign(tmp_path, monkeypatch)

    payload = attach_job_provenance(
        {"campaign_id": campaign.id},
        campaign,
        job_kind="strix_scan",
        action="automated_scan",
    )

    assert payload["_provenance"]["external_policy_provider"] == "hackerone"
    assert (
        payload["_provenance"]["external_policy_fingerprint"]
        == admitted["policy_binding"]["binding_fingerprint"]
    )


def test_hackerone_provenance_rejects_binding_substitution(tmp_path, monkeypatch):
    _, campaign = _admitted_campaign(tmp_path, monkeypatch)
    payload = attach_job_provenance(
        {"campaign_id": campaign.id},
        campaign,
        job_kind="strix_scan",
        action="automated_scan",
    )
    payload["_provenance"]["external_policy_fingerprint"] = "0" * 64
    job = {
        "campaign_id": campaign.id,
        "kind": "strix_scan",
        "payload": payload,
    }

    verification = verify_job_provenance(job, campaign)

    assert verification["valid"] is False
    assert "external_policy_fingerprint_mismatch" in verification["reasons"]


def test_hackerone_conservative_dry_run_queues_one_verified_nuclei_job(tmp_path, monkeypatch):
    db = str(tmp_path / "campaigns.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    queue_db = str(tmp_path / "jobs.sqlite3")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    admitted = admit_hackerone_campaign(_admission_payload())
    campaign_id = admitted["campaign"]["id"]
    jobs = JobQueue(queue_db)
    monkeypatch.setattr(main, "queue", lambda: jobs)

    start_result = main.start_campaign(campaign_id)

    assert start_result["campaign_id"] == campaign_id
    assert start_result["state"] == main.CampaignState.running
    assert start_result["audit_reconciled"] is True
    assert start_result["job"]["kind"] == "nuclei_scan"
    assert start_result["job"]["payload"]["_provenance"]["job_kind"] == "nuclei_scan"
    assert jobs.stats()["total"] == 1

    persisted = Storage(db, artifacts).get_campaign(campaign_id)
    assert persisted is not None
    started = main.Campaign.model_validate(persisted)
    assert started.state == main.CampaignState.running

    started_events = [event for event in started.events if event.get("type") == "campaign_started"]
    assert len(started_events) == 1
    assert started_events[0]["job_id"] == start_result["job"]["id"]

    job = jobs.get(started_events[0]["job_id"])
    assert job is not None
    assert job["status"] == "queued"
    assert job["kind"] == "nuclei_scan"
    verification = verify_job_provenance(job, started)
    assert verification["valid"] is True
    assert verification["reasons"] == []
    assert (
        job["payload"]["_provenance"]["external_policy_fingerprint"]
        == admitted["policy_binding"]["binding_fingerprint"]
    )


def test_non_hackerone_start_keeps_strix_routing(tmp_path, monkeypatch):
    db = str(tmp_path / "campaigns.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    queue_db = str(tmp_path / "jobs.sqlite3")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    campaign = main.Campaign(
        id="manual-campaign",
        state=main.CampaignState.ready,
        target=main.TargetInput(
            name="Manual fixture",
            primary_url="https://example.test",
            rules=main.ProgramRules(
                authorization_reference="manual-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    Storage(db, artifacts).save_campaign(campaign.model_dump(mode="json"))
    jobs = JobQueue(queue_db)
    monkeypatch.setattr(main, "queue", lambda: jobs)

    start_result = main.start_campaign(campaign.id)

    assert start_result["job"]["kind"] == "strix_scan"
    provenance = start_result["job"]["payload"]["_provenance"]
    assert provenance["job_kind"] == "strix_scan"
    assert "external_policy_provider" not in provenance
    assert "external_policy_fingerprint" not in provenance
    assert jobs.stats()["total"] == 1
