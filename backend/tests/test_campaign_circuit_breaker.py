from datetime import datetime, timedelta, timezone

from app.campaign_audit import append_campaign_event, verify_campaign_event_chain
from app.campaign_control import campaign_control_status, reset_campaign_circuit_breaker
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



def test_breaker_reset_endpoint_seals_requested_and_completed_audit_events(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    store = Storage(db, artifacts)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    record_circuit_open(
        store,
        campaign.id,
        "failed job budget exhausted",
        at="2026-09-14T08:00:00+00:00",
    )

    result = reset_campaign_circuit_breaker(campaign.id)
    saved = store.get_campaign(campaign.id)

    assert result["operator_action"] is True
    assert result["audit_reconciled"] is True
    assert result["circuit_breaker"]["open"] is False
    request_id = result["request_id"]
    assert any(
        event.get("type") == "circuit_breaker_reset_requested"
        and event.get("request_id") == request_id
        for event in saved["events"]
    )
    assert any(
        event.get("type") == "circuit_breaker_reset_completed"
        and event.get("request_id") == request_id
        for event in saved["events"]
    )
    assert verify_campaign_event_chain(saved["events"])["valid"] is True

    repeated = reset_campaign_circuit_breaker(campaign.id)
    saved_again = store.get_campaign(campaign.id)
    assert repeated["operator_action"] is False
    assert len(saved_again["events"]) == len(saved["events"])


def test_breaker_reset_reconciles_completion_after_reset_already_happened(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    store = Storage(db, artifacts)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    opened = record_circuit_open(
        store,
        campaign.id,
        "runtime budget exhausted",
        at="2026-09-14T08:10:00+00:00",
    )
    request_id = "breaker-reset:fixture-reconcile"

    raw, version = store.get_campaign_record(campaign.id)
    append_campaign_event(
        raw["events"],
        {
            "type": "circuit_breaker_reset_requested",
            "request_id": request_id,
            "breaker_opened_at": opened["opened_at"],
            "breaker_reason": opened["reason"],
            "at": "2026-09-14T08:11:00+00:00",
        },
    )
    store.save_campaign(raw, expected_version=version)
    record_circuit_reset(
        store,
        campaign.id,
        at="2026-09-14T08:12:00+00:00",
    )

    result = reset_campaign_circuit_breaker(campaign.id)
    saved = store.get_campaign(campaign.id)

    assert result["request_id"] == request_id
    assert result["audit_reconciled"] is True
    assert result["circuit_breaker"]["open"] is False
    assert sum(
        event.get("type") == "circuit_breaker_reset_completed"
        and event.get("request_id") == request_id
        for event in saved["events"]
    ) == 1
    assert verify_campaign_event_chain(saved["events"])["valid"] is True
