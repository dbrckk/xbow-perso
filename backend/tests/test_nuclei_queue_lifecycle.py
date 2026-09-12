import json
from pathlib import Path

import pytest

from app.jobqueue import JobQueue
from app.main import Campaign, ProgramRules, TargetInput
from app.orchestrator import _scan_engines
from app.scanner_worker import run_nuclei_job
from app.storage import Storage


def _campaign():
    return Campaign(
        id="nuclei-campaign",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
            ),
        ),
    )


def test_scan_engines_default_preserves_strix(monkeypatch):
    monkeypatch.delenv("XBOW_SCAN_ENGINES", raising=False)
    assert _scan_engines() == ("strix",)


def test_scan_engines_support_explicit_nuclei_and_fail_closed(monkeypatch):
    monkeypatch.setenv("XBOW_SCAN_ENGINES", "strix,nuclei")
    assert _scan_engines() == ("strix", "nuclei")

    monkeypatch.setenv("XBOW_SCAN_ENGINES", "strix,shell")
    with pytest.raises(ValueError, match="unsupported scanner engine"):
        _scan_engines()


def test_sqlite_queue_accepts_nuclei_scan(tmp_path):
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    job = queue.enqueue(
        "campaign-1",
        "nuclei_scan",
        {"campaign_id": "campaign-1", "target": "https://example.test"},
        dedupe_key="nuclei:1",
    )
    assert job["kind"] == "nuclei_scan"


def test_nuclei_worker_dry_run_preserves_safe_default(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    root = tmp_path / "nuclei-runs"
    monkeypatch.setenv("XBOW_NUCLEI_RUN_ROOT", str(root))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "false")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "false")

    result = run_nuclei_job(
        {"id": "job-1", "campaign_id": campaign.id},
        campaign,
        queue,
        store,
    )

    assert result.status == "dry_run"
    assert result.engine == "nuclei"
    assert result.ingestion is None
    assert result.event["engine"] == "nuclei"
    assert campaign.state.value == "ready"


def test_nuclei_worker_ingests_scoped_findings_and_queues_validation(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    root = tmp_path / "nuclei-runs"
    monkeypatch.setenv("XBOW_NUCLEI_RUN_ROOT", str(root))
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("XBOW_ENABLE_NUCLEI", "true")

    def fake_execute(plan):
        run_dir = Path(plan.output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        item = {
            "template-id": "fixture-template",
            "matched-at": "https://app.example.test/profile",
            "info": {
                "name": "Fixture exposure",
                "severity": "medium",
                "description": "fixture",
            },
        }
        (run_dir / "nuclei.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
        return {
            "engine": "nuclei",
            "status": "completed",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "output_dir": str(run_dir),
            "campaign_rps": 2.0,
            "admission_cap_rps": 2.0,
        }

    monkeypatch.setattr("app.scanner_worker.execute", fake_execute)

    result = run_nuclei_job(
        {"id": "job-2", "campaign_id": campaign.id},
        campaign,
        queue,
        store,
    )

    assert result.status == "completed"
    assert result.ingestion is not None
    assert result.ingestion.findings_seen == 1
    assert result.ingestion.findings_added == 1
    assert result.ingestion.validation_jobs == 1
    assert campaign.findings[0].discovered_by == "nuclei"
    counts = queue.campaign_job_counts(campaign.id)
    assert counts["independent_validation"] == 1
