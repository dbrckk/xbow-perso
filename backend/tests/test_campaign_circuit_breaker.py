from datetime import datetime, timedelta, timezone

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
