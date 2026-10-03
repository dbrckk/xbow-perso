import hashlib
import json
import os
from pathlib import Path

from app.jobqueue import JobQueue
from app.main import Campaign, ProgramRules, TargetInput
from app.scanner_worker import run_strix_job
from app.storage import Storage


def _campaign():
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
            ),
        ),
    )


def test_scanner_worker_dry_run_stays_ready_and_records_event(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    monkeypatch.setenv("XBOW_STRIX_RUN_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "false")
    monkeypatch.setenv("DRY_RUN", "true")

    result = run_strix_job(
        {"id": "job-1", "campaign_id": campaign.id},
        campaign,
        queue,
        store,
    )

    assert result.status == "dry_run"
    assert result.ingestion is None
    assert result.event["type"] == "scan_dry_run"
    assert result.event["engine"] == "strix"
    assert campaign.state.value == "ready"
    observations = store.list_observations(campaign.id)
    assert len(observations) == 1
    assert observations[0]["kind"] == "asset"
    assert observations[0]["source"] == "strix-dry-run"



def test_scanner_worker_binds_status_findings_and_evidence_to_same_strix_run(
    tmp_path,
    monkeypatch,
):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    run_root = tmp_path / "runs"
    monkeypatch.setenv("XBOW_STRIX_RUN_ROOT", str(run_root))
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_MAX_AUTONOMOUS_RPS", "2.0")

    selected_payload = json.dumps(
        {
            "vulnerabilities": [
                {
                    "title": "Selected run finding",
                    "severity": "medium",
                    "asset": "https://app.example.test",
                }
            ]
        }
    )
    newer_artifact_payload = json.dumps(
        {
            "vulnerabilities": [
                {
                    "title": "Different run finding",
                    "severity": "high",
                    "asset": "https://app.example.test",
                }
            ]
        }
    )

    def fake_execute(plan):
        output = Path(plan.output_dir)
        selected = output / "selected-run"
        different = output / "different-run"
        selected.mkdir(parents=True)
        different.mkdir(parents=True)

        selected_run_json = selected / "run.json"
        different_run_json = different / "run.json"
        selected_vulnerabilities = selected / "vulnerabilities.json"
        different_vulnerabilities = different / "vulnerabilities.json"

        selected_run_json.write_text(
            json.dumps({"status": "completed"}),
            encoding="utf-8",
        )
        different_run_json.write_text(
            json.dumps({"status": "stopped"}),
            encoding="utf-8",
        )
        selected_vulnerabilities.write_text(selected_payload, encoding="utf-8")
        different_vulnerabilities.write_text(
            newer_artifact_payload,
            encoding="utf-8",
        )

        os.utime(selected_run_json, (300, 300))
        os.utime(different_run_json, (200, 200))
        os.utime(selected_vulnerabilities, (100, 100))
        os.utime(different_vulnerabilities, (400, 400))

        return {
            "engine": "strix",
            "status": "completed",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "output_dir": str(output),
            "campaign_rps": plan.campaign_rps,
            "admission_cap_rps": plan.admission_cap_rps,
            "sandbox_profile": "restricted-v1",
        }

    monkeypatch.setattr("app.scanner_worker.execute", fake_execute)

    result = run_strix_job(
        {"id": "job-1", "campaign_id": campaign.id},
        campaign,
        queue,
        store,
    )

    assert result.status == "completed"
    assert result.ingestion is not None
    assert result.ingestion.findings_seen == 1
    assert [finding.title for finding in campaign.findings] == ["Selected run finding"]

    evidence = [
        artifact
        for artifact in store.list_artifacts(campaign.id)
        if artifact["kind"] == "http_evidence"
    ]
    assert len(evidence) == 1
    assert evidence[0]["sha256"] == hashlib.sha256(
        selected_payload.encode()
    ).hexdigest()
