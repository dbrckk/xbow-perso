import pytest
from fastapi import HTTPException

from app import main
from app.job_provenance import verify_job_provenance
from app.jobqueue import JobQueue
from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.observation_graph import Observation
from app.storage import Storage


def _campaign(*, findings=None):
    return Campaign(
        id="campaign-api-provenance",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="authorization-1",
                allowed_targets=["example.test"],
                denied_targets=[],
                max_requests_per_second=2.0,
                automated_scanning=True,
            ),
        ),
        findings=findings or [],
    )


def _runtime(tmp_path, monkeypatch, *, campaign=None):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    jobs = JobQueue(db)
    campaign = campaign or _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    monkeypatch.setattr(main, "storage", lambda: store)
    monkeypatch.setattr(main, "queue", lambda: jobs)
    return campaign, store, jobs


def _assert_bound(job, campaign, expected_kind):
    assert job["kind"] == expected_kind
    assert job["payload"]["_provenance"]["schema"] == "job-provenance-v1"
    assert job["payload"]["_provenance"]["job_kind"] == expected_kind
    assert verify_job_provenance(job, campaign)["valid"] is True


def test_campaign_start_direct_enqueue_is_provenanced(tmp_path, monkeypatch):
    campaign, _store, _jobs = _runtime(tmp_path, monkeypatch)

    result = main.start_campaign(campaign.id)
    latest = main.assert_campaign_exists(campaign.id)

    _assert_bound(result["job"], latest, "strix_scan")


def test_add_finding_direct_validation_enqueue_is_provenanced(tmp_path, monkeypatch):
    campaign, _store, jobs = _runtime(tmp_path, monkeypatch)
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        discovered_by="scanner",
    )

    main.add_finding(campaign.id, finding)
    job = jobs.get_by_dedupe(campaign.id, "independent_validation", "validation:f1")
    latest = main.assert_campaign_exists(campaign.id)

    assert job is not None
    _assert_bound(job, latest, "independent_validation")


def test_manual_report_direct_enqueue_is_provenanced(tmp_path, monkeypatch):
    campaign, _store, _jobs = _runtime(tmp_path, monkeypatch)

    job = main.queue_report(campaign.id, platform="generic")
    latest = main.assert_campaign_exists(campaign.id)

    _assert_bound(job, latest, "report")


def test_completion_report_direct_enqueue_is_provenanced(tmp_path, monkeypatch):
    campaign, _store, jobs = _runtime(tmp_path, monkeypatch)
    _document, version = _store.get_campaign_record(campaign.id)

    main._ensure_completion_report(campaign, version)
    job = jobs.get_by_dedupe(campaign.id, "report", "report:generic:completed")
    latest = main.assert_campaign_exists(campaign.id)

    assert job is not None
    _assert_bound(job, latest, "report")


def test_resolution_rejects_observed_validation_without_attached_evidence(tmp_path, monkeypatch):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    campaign, store, _jobs = _runtime(
        tmp_path,
        monkeypatch,
        campaign=_campaign(findings=[finding]),
    )
    store.put_observation(
        campaign.id,
        Observation("finding:f1", "finding", "candidate", "scanner").to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "validator",
            parent_ids=("finding:f1",),
        ).to_dict(),
    )

    with pytest.raises(HTTPException, match="evidence") as exc:
        main.validate_finding(campaign.id, "f1", confirmed=True, validator="validator")

    assert exc.value.status_code == 409


def test_resolution_accepts_evidence_backed_independent_validation(tmp_path, monkeypatch):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    campaign, store, jobs = _runtime(
        tmp_path,
        monkeypatch,
        campaign=_campaign(findings=[finding]),
    )
    store.put_observation(
        campaign.id,
        Observation("finding:f1", "finding", "candidate", "scanner").to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "validator",
            parent_ids=("finding:f1",),
        ).to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "evidence:v1",
            "evidence",
            "validation-artifact",
            "validator",
            parent_ids=("validation:v1",),
        ).to_dict(),
    )

    result = main.validate_finding(campaign.id, "f1", confirmed=True, validator="validator")
    report_job = jobs.get_by_dedupe(campaign.id, "report", "report:generic:completed")
    latest = main.assert_campaign_exists(campaign.id)

    assert result.status == "confirmed"
    assert report_job is not None
    _assert_bound(report_job, latest, "report")
