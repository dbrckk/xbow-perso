import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import scanner_worker, worker_service
from app.jobqueue import JobQueue
from app.main import app
from app.storage import Storage
from app.validator import ProbeResult


TOKEN = "h1-report-e2e-token-" + "a" * 32


def _resource(identifier: str):
    return {
        "type": "structured-scope",
        "attributes": {
            "asset_identifier": identifier,
            "asset_type": "Domain",
            "eligible_for_submission": True,
        },
    }


def _launch_payload():
    return {
        "document": {"data": [_resource("example.com")]},
        "policy": {
            "authorization_reference": "H1-REPORT-E2E",
            "policy_version": "2026-09-18",
            "reviewed_at": "2026-09-18T19:00:00+02:00",
            "reviewed_by": "e2e-human-reviewer",
            "safe_harbor_confirmed": True,
            "automated_scanning": True,
            "max_requests_per_second": 1.0,
            "test_account_required": False,
            "test_account_constraints": "",
            "additional_restrictions": [],
            "program_notes": "Deterministic E2E fixture for the governed HackerOne report lifecycle.",
        },
        "target": {
            "name": "Authorized HackerOne report E2E",
            "primary_url": "https://example.com",
        },
    }


def _headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_hackerone_full_lifecycle_produces_downloadable_report(
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
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")
    monkeypatch.setenv("XBOW_MAX_AUTONOMOUS_RPS", "2.0")
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_API_TOKEN_FILE", raising=False)
    monkeypatch.setenv("XBOW_API_TOKEN", TOKEN)
    monkeypatch.setenv("XBOW_TOTP_ENABLED", "false")

    def fake_execute(plan):
        run_dir = Path(plan.output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        finding = {
            "template-id": "h1-report-e2e-exposure",
            "matched-at": "https://example.com/profile",
            "info": {
                "name": "HackerOne E2E exposure",
                "severity": "medium",
                "description": "Synthetic scanner result for the governed E2E test.",
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
            "stdout": "e2e nuclei execution completed",
            "stderr": "",
            "output_dir": str(run_dir),
            "campaign_rps": plan.campaign_rps,
            "admission_cap_rps": plan.admission_cap_rps,
        }

    monkeypatch.setattr(scanner_worker, "execute", fake_execute)
    monkeypatch.setattr(
        worker_service,
        "safe_http_probe",
        lambda campaign, finding: ProbeResult(
            status="observed",
            url=str(finding.endpoint),
            http_status=200,
            content_type="text/html",
            body_preview="synthetic bounded validation evidence",
        ),
    )
    monkeypatch.setattr(
        worker_service,
        "advance_campaign",
        lambda campaign, queue, store: {"action": {"kind": "stop"}},
    )

    client = TestClient(app)
    launch = client.post(
        "/api/imports/hackerone/campaigns/launch",
        headers=_headers(),
        json=_launch_payload(),
    )

    assert launch.status_code == 200
    launched = launch.json()
    campaign_id = launched["campaign"]["id"]
    scan_job = launched["start"]["job"]
    assert scan_job["kind"] == "nuclei_scan"
    assert scan_job["payload"]["_provenance"]["external_policy_provider"] == "hackerone"

    queue = JobQueue(db)
    store = Storage(db, artifacts)

    monkeypatch.setenv("XBOW_WORKER_ROLE", "scanner")
    assert worker_service.process_one(queue, store, "e2e-scanner") is True
    assert queue.get(scan_job["id"])["status"] == "completed"

    campaign = store.get_campaign(campaign_id)
    assert campaign is not None
    assert campaign["state"] == "validating"
    assert len(campaign["findings"]) == 1
    finding = campaign["findings"][0]
    assert finding["status"] == "validation_required"
    assert finding["discovered_by"] == "nuclei"

    monkeypatch.setenv("XBOW_WORKER_ROLE", "general")
    assert worker_service.process_one(queue, store, "e2e-validator") is True

    validation_job = queue.get_by_dedupe(
        campaign_id,
        "independent_validation",
        f"validation:{finding['id']}",
    )
    assert validation_job is not None
    assert validation_job["status"] == "completed"
    assert validation_job["payload"]["_provenance"]["external_policy_provider"] == "hackerone"

    review = client.put(
        f"/api/campaigns/{campaign_id}/findings/{finding['id']}/review-metadata",
        headers=_headers(),
        json={
            "summary": "Profile metadata is exposed to an unauthorized requester.",
            "impact": "An attacker could disclose private profile metadata.",
            "reproduction_steps": [
                "Open the affected profile endpoint without an authenticated session.",
                "Observe the profile metadata returned by the endpoint.",
            ],
            "remediation": "Require authorization before returning profile metadata.",
            "cwe": "CWE-200",
            "cvss": 5.3,
            "reviewer": "e2e-human-reviewer",
        },
    )
    assert review.status_code == 200
    assert review.json()["status"] == "validation_required"

    confirm = client.post(
        f"/api/campaigns/{campaign_id}/findings/{finding['id']}/validate",
        headers=_headers(),
        params={"confirmed": "true", "validator": "e2e-human-reviewer"},
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "confirmed"
    assert confirm.json()["validated_by"] == "e2e-human-reviewer"

    report_request = client.post(
        f"/api/campaigns/{campaign_id}/reports",
        headers=_headers(),
        params={"platform": "hackerone"},
    )
    assert report_request.status_code == 200
    hackerone_job = report_request.json()
    assert hackerone_job["kind"] == "report"
    assert hackerone_job["payload"]["platform"] == "hackerone"
    assert hackerone_job["payload"]["_provenance"]["external_policy_provider"] == "hackerone"

    for _ in range(5):
        if not worker_service.process_one(queue, store, "e2e-report-worker"):
            break
    else:
        raise AssertionError("report queue did not drain within bounded iterations")

    assert queue.get(hackerone_job["id"])["status"] == "completed"

    report_artifacts = [
        item
        for item in store.list_artifacts(campaign_id)
        if item["kind"] == "report"
    ]
    assert report_artifacts

    hackerone_artifact = None
    hackerone_text = ""
    for artifact in report_artifacts:
        _metadata, body = store.read_artifact(campaign_id, artifact["id"])
        text = body.decode("utf-8")
        if "Submission format:** HackerOne" in text:
            hackerone_artifact = artifact
            hackerone_text = text
            break

    assert hackerone_artifact is not None
    assert "HackerOne E2E exposure" in hackerone_text
    assert "Profile metadata is exposed to an unauthorized requester." in hackerone_text
    assert "An attacker could disclose private profile metadata." in hackerone_text
    assert "CWE-200" in hackerone_text
    assert "5.3" in hackerone_text

    download = client.get(
        f"/api/campaigns/{campaign_id}/artifacts/{hackerone_artifact['id']}",
        headers=_headers(),
    )
    assert download.status_code == 200
    assert download.headers["x-content-sha256"] == hackerone_artifact["sha256"]
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.text == hackerone_text

    persisted = store.get_campaign(campaign_id)
    assert persisted is not None
    event_types = [event.get("type") for event in persisted["events"]]
    assert "hackerone_policy_bound" in event_types
    assert "scanner_results_ingested" in event_types
    assert "finding_review_metadata_updated" in event_types
    assert "finding_validated" in event_types
    assert "report_queued" in event_types
    assert "report_generated" in event_types
