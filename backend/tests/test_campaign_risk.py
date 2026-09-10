from app.campaign_risk import build_campaign_risk, campaign_risk
from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def test_campaign_risk_escalates_on_scope_integrity_and_low_coverage():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://outside.test/account?id=secret",
            "recon",
            parent_ids=("asset:a",),
        )
    )

    risk = build_campaign_risk([], graph, scope_checker=lambda host: host == "example.test")

    assert risk.blocked is True
    assert "scope_or_surface_integrity" in risk.factors
    assert "low_review_coverage" in risk.factors
    assert risk.next_focus == "scope_integrity"
    assert risk.level in {"high", "critical"}
    assert "secret" not in str(risk.to_dict())


def test_campaign_risk_reflects_high_impact_unvalidated_finding():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("asset:a",),
        )
    )
    finding = Finding(
        id="f1",
        title="fixture",
        severity="critical",
        asset="https://example.test",
        summary="bounded fixture",
        status="validation_required",
        discovered_by="scanner",
    )

    risk = build_campaign_risk([finding], graph)

    assert "high_impact_findings" in risk.factors
    assert "unvalidated_findings" in risk.factors
    assert risk.next_focus == "validate_findings"
    assert risk.score > 0


def test_campaign_risk_route_is_exposed_and_advisory(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="risk-1",
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
    store.put_observation(
        campaign.id,
        Observation("asset:a", "asset", "example.test", "recon").to_dict(),
    )

    result = campaign_risk(campaign.id)

    assert "/api/campaigns/{campaign_id}/risk" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["advisory_only"] is True
    assert result["scope_aware"] is True
