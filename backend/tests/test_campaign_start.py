from app.campaign_start import start_via_orchestrator
from app.jobqueue import JobQueue
from app.main import Campaign, ProgramRules, TargetInput
from app.storage import Storage


def _campaign():
    return Campaign(
        id="start-loop",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )


def test_start_via_orchestrator_queues_recon_before_scanner(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    result = start_via_orchestrator(campaign, queue, store)

    planner = result["planner"]
    jobs = result["jobs"]
    assert planner["action"]["kind"] == "crawl"
    assert jobs
    assert all(job["kind"] == "recon_task" for job in jobs)
    assert not any(job["kind"] in {"strix_scan", "nuclei_scan"} for job in jobs)
    assert result["primary_job"]["id"] == jobs[0]["id"]


def test_start_via_orchestrator_is_idempotent_for_initial_recon_jobs(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    first = start_via_orchestrator(campaign, queue, store)
    second = start_via_orchestrator(campaign, queue, store)

    assert second["planner"]["job_ids"] == first["planner"]["job_ids"]
    assert queue.stats()["total"] == len(first["jobs"])


def test_start_via_orchestrator_remains_dry_run_safe_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_RECON", raising=False)
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    result = start_via_orchestrator(campaign, queue, store)

    assert result["planner"]["action"]["kind"] == "crawl"
    assert all(job["kind"] == "recon_task" for job in result["jobs"])
