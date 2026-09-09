from app.jobqueue import JobQueue
from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.observation_graph import Observation
from app.orchestrator import advance_campaign
from app.storage import Storage


def make_campaign(*, automated_scanning=True, findings=None):
    return Campaign(
        id="c1",
        target=TargetInput(
            name="demo",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
                automated_scanning=automated_scanning,
            ),
        ),
        findings=findings or [],
    )


def test_advance_bootstraps_target_and_queues_one_scan(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    first = advance_campaign(campaign, queue, store)
    second = advance_campaign(campaign, queue, store)

    assert first["action"]["kind"] == "scan"
    assert len(first["job_ids"]) == 1
    assert second["job_ids"] == first["job_ids"]
    assert queue.stats()["total"] == 1
    assert {item["kind"] for item in store.list_observations(campaign.id)} == {"asset", "endpoint"}


def test_advance_stops_when_automation_disabled(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign(automated_scanning=False)
    store.save_campaign(campaign.model_dump(mode="json"))

    result = advance_campaign(campaign, queue, store)

    assert result["action"]["kind"] == "stop"
    assert result["job_ids"] == []
    assert queue.stats()["total"] == 0


def test_advance_queues_only_unvalidated_findings_then_report(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    findings = [
        Finding(
            id="f1",
            title="candidate one",
            severity="low",
            asset="https://example.test",
            summary="one",
            discovered_by="scanner",
        ),
        Finding(
            id="f2",
            title="candidate two",
            severity="low",
            asset="https://example.test",
            summary="two",
            discovered_by="scanner",
        ),
    ]
    campaign = make_campaign(findings=findings)
    store.save_campaign(campaign.model_dump(mode="json"))
    asset = Observation("a1", "asset", "example.test", "scanner")
    store.put_observation(campaign.id, asset.to_dict())
    for finding in findings:
        store.put_observation(
            campaign.id,
            Observation(
                f"finding:{finding.id}",
                "finding",
                finding.id,
                "scanner",
                parent_ids=("a1",),
            ).to_dict(),
        )
    store.put_observation(
        campaign.id,
        Observation("v1", "validation", "observed", "validator", parent_ids=("finding:f1",)).to_dict(),
    )

    result = advance_campaign(campaign, queue, store)
    queued = queue.get(result["job_ids"][0])
    assert result["action"]["kind"] == "validate"
    assert queued["payload"]["finding_id"] == "f2"

    store.put_observation(
        campaign.id,
        Observation("v2", "validation", "observed", "validator", parent_ids=("finding:f2",)).to_dict(),
    )
    report = advance_campaign(campaign, queue, store)
    report_job = queue.get(report["job_ids"][0])
    assert report["action"]["kind"] == "report"
    assert report_job["kind"] == "report"
