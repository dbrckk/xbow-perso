from datetime import datetime, timedelta, timezone

from app.campaign_control import campaign_control_status
from app.campaign_runtime import CampaignRuntimeLimit
from app.circuit_breaker import circuit_breaker_state, record_circuit_open, record_circuit_reset
from app.jobqueue import JobQueue
from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import ObservationGraph
from app.orchestrator import advance_campaign
from app.storage import Storage


def _campaign():
    return Campaign(
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="authorized-test",
                allowed_targets=["example.test"],
            ),
        )
    )


def test_circuit_breaker_persists_and_resets(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    opened = record_circuit_open(
        store,
        campaign.id,
        "failed job budget exhausted",
        at="2026-09-14T07:00:00+00:00",
    )
    graph = ObservationGraph.from_records(store.list_observations(campaign.id))

    assert opened["open"] is True
    assert circuit_breaker_state(graph)["reason"] == "failed job budget exhausted"

    reset = record_circuit_reset(
        store,
        campaign.id,
        at="2026-09-14T07:01:00+00:00",
    )
    graph = ObservationGraph.from_records(store.list_observations(campaign.id))

    assert reset["open"] is False
    assert circuit_breaker_state(graph)["open"] is False
    assert circuit_breaker_state(graph)["reset_at"] == "2026-09-14T07:01:00+00:00"


def test_runtime_exhaustion_opens_breaker_and_future_advance_stays_blocked(tmp_path):
    db = str(tmp_path / "db.sqlite3")
    store = Storage(db, str(tmp_path / "artifacts"))
    queue = JobQueue(db)
    campaign = _campaign()
    campaign.created_at = (
        datetime.now(timezone.utc) - timedelta(minutes=2)
    ).isoformat()
    store.save_campaign(campaign.model_dump(mode="json"))

    first = advance_campaign(
        campaign,
        queue,
        store,
        runtime_limit=CampaignRuntimeLimit(max_runtime_seconds=60),
    )
    assert first["action"]["reason"] == "campaign runtime budget exhausted"

    graph = ObservationGraph.from_records(store.list_observations(campaign.id))
    breaker = circuit_breaker_state(graph)
    assert breaker["open"] is True

    campaign.created_at = datetime.now(timezone.utc).isoformat()
    second = advance_campaign(
        campaign,
        queue,
        store,
        runtime_limit=CampaignRuntimeLimit(max_runtime_seconds=3600),
    )

    assert second["action"]["kind"] == "stop"
    assert second["action"]["reason"].startswith("circuit breaker open:")
    assert second["job_ids"] == []


def test_control_routes_are_exposed():
    paths = app.openapi()["paths"]

    assert "/api/campaigns/{campaign_id}/control-status" in paths
    assert "/api/campaigns/{campaign_id}/circuit-breaker/reset" in paths



def test_control_status_reports_budget_blocker_consistently(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_PLANNER_MAX_FAILED_JOBS", "1")

    store = Storage(db, artifacts)
    queue = JobQueue(db)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))

    job = queue.enqueue(
        campaign.id,
        "report",
        {"campaign_id": campaign.id, "platform": "generic"},
        max_attempts=1,
        dedupe_key="fixture:failed-control-status",
    )
    claimed = queue.claim("fixture-worker")
    assert claimed is not None and claimed["id"] == job["id"]
    queue.finish(claimed["id"], "fixture-worker", False, "fixture failure")

    result = campaign_control_status(campaign.id)

    assert result["autonomy_blocked"] is True
    assert result["autonomy_block_reasons"] == ["budget_blocked"]
    assert result["budget"]["usage"]["failed_jobs"] == 1
    assert result["budget"]["usage"]["blocked_actions"]["scan"] == "failed job budget exhausted"



def test_control_status_exposes_scanner_stability_and_recon_telemetry(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "false")
    monkeypatch.setenv("DRY_RUN", "true")
    campaign = _campaign()
    campaign.events.extend(
        [
            {
                "type": "recon_task_completed",
                "requests_made": 3,
                "bytes_read": 1200,
                "max_depth_reached": 2,
                "skipped_out_of_scope": 1,
                "skipped_cross_origin": 2,
                "wall_time_seconds": 1.25,
                "stopped_by_time_budget": True,
                "frontier_remaining": 3,
                "stopped_by_request_budget": False,
                "deferred_by_request_budget": 0,
                "coverage_complete": False,
            },
            {
                "type": "recon_task_completed",
                "requests_made": 2,
                "bytes_read": 800,
                "max_depth_reached": 1,
                "skipped_out_of_scope": 0,
                "skipped_cross_origin": 1,
                "wall_time_seconds": 0.75,
                "stopped_by_time_budget": False,
                "frontier_remaining": 0,
                "stopped_by_request_budget": True,
                "deferred_by_request_budget": 4,
                "coverage_complete": False,
            },
        ]
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"))

    from app.campaign_control import campaign_control_status

    result = campaign_control_status(campaign.id)

    assert result["scanner_execution"]["dispatch_ready"] is False
    assert result["planner_stability"]["state"] == "stable"
    assert result["recon_telemetry"] == {
        "completed_tasks": 2,
        "requests_made": 5,
        "bytes_read": 2000,
        "max_depth_reached": 2,
        "skipped_out_of_scope": 1,
        "skipped_cross_origin": 3,
        "wall_time_seconds": 2.0,
        "time_budget_stops": 1,
        "request_budget_stops": 1,
        "incomplete_tasks": 2,
        "frontier_remaining": 3,
        "deferred_by_request_budget": 4,
    }
