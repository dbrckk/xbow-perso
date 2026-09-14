from app.main import Campaign, ProgramRules, TargetInput, campaign_plan
from app.storage import Storage


def test_campaign_plan_uses_configured_budget_and_exposes_evidence_quality(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    monkeypatch.setenv("XBOW_PLANNER_MAX_ACTIONS", "7")

    campaign = Campaign(
        id="plan-quality-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    result = campaign_plan(campaign.id)

    assert result["budget"]["limits"]["max_actions"] == 7
    assert result["evidence_quality"] == []
    assert result["read_only"] is True
