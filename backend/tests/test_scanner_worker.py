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
