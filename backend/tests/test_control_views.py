from app.main import (
    Campaign,
    Finding,
    ProgramRules,
    TargetInput,
    campaign_knowledge,
    campaign_plan,
    list_agents,
    list_campaign_observations,
)
from app.observation_graph import Observation
from app.storage import Storage


def _campaign() -> Campaign:
    return Campaign(
        id="c1",
        target=TargetInput(
            name="demo",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            Finding(
                id="f1",
                title="candidate",
                severity="high",
                asset="https://example.test",
                summary="demo",
                discovered_by="scanner",
            )
        ],
    )


def _configure(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    store = Storage(db, artifacts)
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"))
    store.put_observation(
        campaign.id,
        Observation("a1", "asset", "example.test", "scope").to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation("e1", "endpoint", "https://example.test", "recon", parent_ids=("a1",)).to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)).to_dict(),
    )
    return store, campaign


def test_agent_catalog_exposes_bounded_roles():
    agents = list_agents()
    roles = {item["role"] for item in agents}
    assert roles == {"control", "recon", "analysis", "validation", "reporting"}


def test_observation_and_knowledge_views_are_read_only(tmp_path, monkeypatch):
    store, campaign = _configure(tmp_path, monkeypatch)
    before = len(store.list_observations(campaign.id))

    observations = list_campaign_observations(campaign.id)
    knowledge = campaign_knowledge(campaign.id)

    assert len(observations) == before
    assert knowledge["snapshot"]["findings"] == 1
    assert knowledge["priorities"][0]["finding_id"] == "f1"
    assert len(store.list_observations(campaign.id)) == before


def test_plan_view_does_not_enqueue_or_persist_decisions(tmp_path, monkeypatch):
    store, campaign = _configure(tmp_path, monkeypatch)
    before = len(store.list_observations(campaign.id))

    plan = campaign_plan(campaign.id)

    assert plan["read_only"] is True
    assert plan["actions"][0]["kind"] == "validate"
    assert plan["agents"][0]["role"] == "validation"
    assert plan["priorities"][0]["finding_id"] == "f1"
    assert len(store.list_observations(campaign.id)) == before
