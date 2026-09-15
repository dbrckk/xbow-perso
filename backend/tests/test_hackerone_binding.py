import pytest
from fastapi import HTTPException

from app import main
from app.hackerone_api import HackerOneCampaignAdmissionInput, admit_hackerone_campaign
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
