import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import scanner_worker, worker_service
from app.hackerone_api import router as hackerone_router
from app.jobqueue import JobQueue
from app.main import Campaign
from app.observation_graph import Observation
from app.orchestrator import advance_campaign
from app.recon_worker import ReconResult
from app.storage import Storage


def _resource(identifier: str, eligible: bool = True):
    return {
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": "Domain",
            "eligible_for_submission": eligible,
        },
    }


def _launch_payload():
    return {
        "document": {"data": [_resource("example.com")]},
        "policy": {
            "authorization_reference": "H1-E2E-42",
            "policy_version": "2026-09-18",
            "reviewed_at": "2026-09-18T18:00:00+02:00",
            "reviewed_by": "e2e-reviewer",
            "safe_harbor_confirmed": True,
            "automated_scanning": True,
            "max_requests_per_second": 1.0,
            "test_account_required": False,
            "test_account_constraints": "",
            "additional_restrictions": [],
            "program_notes": "E2E fixture with explicit automated scanning authorization.",
        },
        "target": {
            "name": "Authorized HackerOne E2E program",
            "primary_url": "https://example.com",
        },
    }


def test_hackerone_launch_reaches_nuclei_ingestion_and_validation_queue(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "e2e.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    run_root = tmp_path / "nuclei-runs"

    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")
    monkeypatch.setenv("XBOW_NUCLEI_RUN_ROOT", str(run_root))
    monkeypatch.setenv("XBOW_WORKER_ROLE", "scanner")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("XBOW_SCAN_ENGINES", "nuclei")
    monkeypatch.setenv("XBOW_MAX_AUTONOMOUS_RPS", "2.0")

    def fake_execute(plan):
        run_dir = Path(plan.output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        finding = {
            "template-id": "e2e-exposure",
            "matched-at": "https://example.com/profile",
            "info": {
                "name": "E2E fixture exposure",
                "severity": "medium",
                "description": "Synthetic scanner result used to prove the governed pipeline.",
            },
        }
        (run_dir / "nuclei.jsonl").write_text(
            json.dumps(finding) + "\n",
            encoding="utf-8",
        )
        return {
            "engine": "nuclei",
            "status": "completed",
            "returncode": 0,
            "stdout": "e2e nuclei scan completed",
            "stderr": "",
            "output_dir": str(run_dir),
            "campaign_rps": plan.campaign_rps,
            "admission_cap_rps": plan.admission_cap_rps,
        }

    monkeypatch.setattr(scanner_worker, "execute", fake_execute)

    api = FastAPI()
    api.include_router(hackerone_router)

    launch = TestClient(api).post(
        "/api/imports/hackerone/campaigns/launch",
        json=_launch_payload(),
    )

    assert launch.status_code == 200
    launched = launch.json()
    campaign_id = launched["campaign"]["id"]
    assert launched["start"]["job"]["kind"] == "recon_task"
    assert launched["start"]["planner"]["action"]["kind"] == "crawl"
    assert launched["campaign"]["state"] == "running"

    queue = JobQueue(db)
    store = Storage(db, artifacts)

    for _ in launched["start"]["planner"]["job_ids"]:
        recon_job = queue.claim_allowed("e2e-recon-fixture", ("recon_task",))
        assert recon_job is not None
        queue.finish(recon_job["id"], "e2e-recon-fixture", True)

    asset = next(
        item for item in store.list_observations(campaign_id)
        if item["kind"] == "asset"
    )
    store.put_observation(
        campaign_id,
        Observation(
            "e2e-endpoint",
            "endpoint",
            "https://example.com/",
            "recon:crawl",
            parent_ids=(asset["id"],),
        ).to_dict(),
    )
    store.put_observation(
        campaign_id,
        Observation(
            "e2e-tech",
            "technology",
            "Server:fixture",
            "recon:detect_technology",
            parent_ids=(asset["id"],),
        ).to_dict(),
    )
    campaign = Campaign.model_validate(store.get_campaign(campaign_id))
    scan_plan = advance_campaign(campaign, queue, store)
    assert scan_plan["action"]["kind"] == "scan"
    assert len(scan_plan["job_ids"]) == 1
    scan_job = queue.get(scan_plan["job_ids"][0])
    assert scan_job is not None
    assert scan_job["kind"] == "nuclei_scan"

    assert worker_service.process_one(queue, store, "e2e-scanner") is True

    finished_scan = queue.get(scan_job["id"])
    assert finished_scan is not None
    assert finished_scan["last_error"] is None, finished_scan["last_error"]
    assert finished_scan["status"] == "completed"
    assert finished_scan["attempts"] == 1

    persisted = store.get_campaign(campaign_id)
    assert persisted is not None
    assert persisted["state"] == "validating"
    assert len(persisted["findings"]) == 1

    finding = persisted["findings"][0]
    assert finding["discovered_by"] == "nuclei"
    assert finding["status"] == "validation_required"
    assert finding["asset"] == "https://example.com"
    assert finding["endpoint"] == "https://example.com/profile"

    event_types = [event.get("type") for event in persisted["events"]]
    assert "hackerone_policy_bound" in event_types
    assert "campaign_started" in event_types
    assert "scanner_results_ingested" in event_types

    counts = queue.campaign_job_counts(campaign_id)
    assert counts["nuclei_scan"] == 1
    assert counts["independent_validation"] == 1

    validation_job = queue.get_by_dedupe(
        campaign_id,
        "independent_validation",
        f"validation:{finding['id']}",
    )
    assert validation_job is not None
    provenance = validation_job["payload"]["_provenance"]
    assert provenance["job_kind"] == "independent_validation"
    assert provenance["action"] == "validate"
    assert provenance["external_policy_provider"] == "hackerone"

    artifacts_written = store.list_artifacts(campaign_id)
    assert any(item["kind"] == "scanner_stdout" for item in artifacts_written)

    evidence = [
        item for item in artifacts_written if item["kind"] == "http_evidence"
    ]
    assert len(evidence) == 1
    metadata, content = store.read_artifact(campaign_id, evidence[0]["id"])
    assert metadata["media_type"] == "application/x-ndjson"
    assert b'"template-id": "e2e-exposure"' in content

    observations = store.list_observations(campaign_id)
    assert any(
        item["kind"] == "evidence"
        and item["source"] == "nuclei"
        and item["metadata"].get("phase") == "scan"
        for item in observations
    )


def test_hackerone_worker_automatically_advances_from_recon_to_nuclei(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "auto-recon.sqlite3")
    artifacts = str(tmp_path / "artifacts")

    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite")
    monkeypatch.setenv("XBOW_WORKER_ROLE", "general")
    monkeypatch.setenv("XBOW_ENABLE_RECON", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("XBOW_SCAN_ENGINES", "nuclei")
    monkeypatch.setenv("XBOW_MAX_AUTONOMOUS_RPS", "2.0")

    def fake_recon(campaign, payload):
        return ReconResult(
            status="observed",
            target=str(campaign.target.primary_url),
            endpoints=(str(campaign.target.primary_url),),
            technologies=("Server:fixture",),
            http_status=200,
            requests_made=1,
            request_budget=1,
            coverage_complete=True,
        )

    monkeypatch.setattr(worker_service, "execute_recon_task", fake_recon)

    api = FastAPI()
    api.include_router(hackerone_router)
    launch = TestClient(api).post(
        "/api/imports/hackerone/campaigns/launch",
        json=_launch_payload(),
    )

    assert launch.status_code == 200, launch.text
    launched = launch.json()
    campaign_id = launched["campaign"]["id"]
    assert launched["start"]["job"]["kind"] == "recon_task"

    queue = JobQueue(db)
    store = Storage(db, artifacts)

    for _ in range(len(launched["start"]["planner"]["job_ids"])):
        assert worker_service.process_one(queue, store, "auto-general") is True

    counts = queue.campaign_job_counts(campaign_id)
    assert counts["nuclei_scan"] == 1
    scan_status = queue.campaign_job_status_counts(campaign_id)
    assert scan_status["queued"] >= 1
