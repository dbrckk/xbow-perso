from datetime import datetime, timedelta, timezone

from app.campaign_runtime import CampaignRuntimeLimit
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
    assert first["agent"]["role"] == "analysis"
    assert len(first["job_ids"]) == 1
    assert second["job_ids"] == first["job_ids"]
    assert queue.stats()["total"] == 1
    assert {item["kind"] for item in store.list_observations(campaign.id)} == {"asset", "endpoint", "evidence"}
    assert first["memory"]["assets"] == 1
    assert first["memory"]["endpoints"] == 1
    assert first["decision_history"][0]["action"] == "scan"


def test_advance_stops_when_automation_disabled(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign(automated_scanning=False)
    store.save_campaign(campaign.model_dump(mode="json"))

    result = advance_campaign(campaign, queue, store)

    assert result["action"]["kind"] == "stop"
    assert result["agent"]["role"] == "control"
    assert result["job_ids"] == []
    assert result["decision_history"][0]["action"] == "stop"
    assert queue.stats()["total"] == 0


def test_advance_stops_when_runtime_budget_is_exhausted(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    campaign.created_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    store.save_campaign(campaign.model_dump(mode="json"))

    result = advance_campaign(
        campaign,
        queue,
        store,
        runtime_limit=CampaignRuntimeLimit(max_runtime_seconds=60),
    )

    assert result["action"]["kind"] == "stop"
    assert result["action"]["reason"] == "campaign runtime budget exhausted"
    assert result["agent"]["role"] == "control"
    assert result["job_ids"] == []
    assert queue.stats()["total"] == 0


def test_advance_queues_only_unvalidated_findings_then_waits_for_resolution_and_reports(tmp_path):
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
    assert result["agent"]["role"] == "validation"
    assert queued["payload"]["finding_id"] == "f2"
    confidence = {item["finding_id"]: item["score"] for item in result["memory"]["finding_confidence"]}
    assert confidence["finding:f1"] == 0.75
    assert confidence["finding:f2"] == 0.35

    store.put_observation(
        campaign.id,
        Observation("v2", "validation", "observed", "validator", parent_ids=("finding:f2",)).to_dict(),
    )
    waiting = advance_campaign(campaign, queue, store)
    assert waiting["action"]["kind"] == "stop"
    assert "explicit confirmation or rejection" in waiting["action"]["reason"]
    assert waiting["job_ids"] == []

    for item in campaign.findings:
        item.status = "confirmed"
        item.validated_by = "validator"
    report = advance_campaign(campaign, queue, store)
    assert report["action"]["kind"] == "stop"
    assert "human review required" in report["action"]["reason"]
    assert report["agent"]["role"] == "control"
    assert report["job_ids"] == []
    assert report["intelligence"]["cycle"]["requires_human"] is True


def test_validation_jobs_are_ordered_by_adaptive_priority(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    findings = [
        Finding(
            id="low",
            title="low candidate",
            severity="low",
            asset="https://example.test",
            summary="low",
            discovered_by="scanner",
        ),
        Finding(
            id="high",
            title="high candidate",
            severity="high",
            asset="https://example.test",
            summary="critical",
            discovered_by="scanner",
        ),
    ]
    campaign = make_campaign(findings=findings)
    store.save_campaign(campaign.model_dump(mode="json"))
    store.put_observation(campaign.id, Observation("a1", "asset", "example.test", "scanner").to_dict())
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

    result = advance_campaign(campaign, queue, store)
    queued = [queue.get(job_id) for job_id in result["job_ids"]]

    assert [job["payload"]["finding_id"] for job in queued] == ["high", "low"]


def test_validation_priority_prefers_less_supported_hypothesis_on_tie(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    findings = [
        Finding(
            id="f1",
            title="candidate one",
            severity="high",
            asset="https://example.test",
            summary="one",
            discovered_by="scanner",
        ),
        Finding(
            id="f2",
            title="candidate two",
            severity="high",
            asset="https://example.test",
            summary="two",
            discovered_by="scanner",
        ),
    ]
    campaign = make_campaign(findings=findings)
    store.save_campaign(campaign.model_dump(mode="json"))
    store.put_observation(campaign.id, Observation("a1", "asset", "example.test", "scanner").to_dict())
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
        Observation(
            "v1",
            "validation",
            "dry_run",
            "validator",
            parent_ids=("finding:f1",),
        ).to_dict(),
    )

    result = advance_campaign(campaign, queue, store)
    queued = [queue.get(job_id) for job_id in result["job_ids"]]

    assert [job["payload"]["finding_id"] for job in queued] == ["f2", "f1"]
    hypotheses = {item["finding_id"]: item for item in result["hypotheses"]}
    assert hypotheses["f1"]["status"] == "partially_supported"
    assert hypotheses["f2"]["status"] == "unvalidated"



def test_orchestrator_exposes_integrated_intelligence_context(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    result = advance_campaign(campaign, queue, store)

    intelligence = result["intelligence"]
    assert intelligence is not None
    assert intelligence["cycle"]["safe_to_progress"] is True
    assert intelligence["gate"]["safe_autonomy_ready"] is True
    assert intelligence["risk"]["level"] in {"low", "moderate"}
    assert intelligence["consensus"]["blocked"] is False
    assert intelligence["read_only_context"] is True
    assert isinstance(intelligence["recon_plan"], list)


def test_orchestrator_gate_blocks_progress_after_failed_job(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    failed = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=1,
        dedupe_key="fixture:failed-job",
    )
    claimed = queue.claim("fixture-worker")
    assert claimed is not None and claimed["id"] == failed["id"]
    queue.finish(claimed["id"], "fixture-worker", False, "fixture failure")

    result = advance_campaign(campaign, queue, store)

    assert result["action"]["kind"] == "stop"
    assert result["job_ids"] == []
    assert "failed_jobs" in result["intelligence"]["gate"]["blockers"]
    assert result["intelligence"]["cycle"]["state"] == "halt"


def test_orchestrator_learning_memory_reaches_adaptive_cycle(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = make_campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    store.put_observation(
        campaign.id,
        Observation("a1", "asset", "example.test", "fixture").to_dict(),
    )
    for index in range(2):
        store.put_observation(
            campaign.id,
            Observation(
                f"e{index}",
                "evidence",
                f"attempt-{index}",
                f"validator-{index}",
                parent_ids=("a1",),
                metadata={
                    "technique": "bounded-review",
                    "outcome": "failure",
                },
            ).to_dict(),
        )

    result = advance_campaign(campaign, queue, store)

    assert "bounded-review" in result["intelligence"]["cycle"]["retry_suppressed_techniques"]
    memory = {
        item["technique"]: item
        for item in result["intelligence"]["learning_memory"]
    }
    assert memory["bounded-review"]["failures"] == 2
