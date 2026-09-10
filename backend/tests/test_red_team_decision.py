from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.red_team_decision import build_red_team_decisions, campaign_red_team_decisions
from app.storage import Storage


def test_decision_engine_prioritizes_scope_integrity():
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

    decisions = build_red_team_decisions(
        [],
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert decisions[0].kind == "scope_integrity"
    assert decisions[0].priority == 1.0
    assert decisions[0].blocked_from_execution is True
    assert "secret" not in str([item.to_dict() for item in decisions])


def test_decision_engine_prioritizes_validation_and_evidence():
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

    decisions = build_red_team_decisions([finding], graph)

    kinds = [item.kind for item in decisions]
    assert kinds[0] == "validate_findings"
    assert "strengthen_evidence" in kinds
    assert all(item.blocked_from_execution is True for item in decisions)


def test_decision_engine_becomes_idle_when_no_work_exists():
    decisions = build_red_team_decisions([], ObservationGraph())

    assert len(decisions) == 1
    assert decisions[0].kind == "idle"
    assert decisions[0].priority == 0.0


def test_decision_route_is_exposed_and_scope_aware(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="decision-1",
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

    result = campaign_red_team_decisions(campaign.id)

    assert "/api/campaigns/{campaign_id}/red-team-decisions" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["advisory_only"] is True
    assert result["scope_aware"] is True


def test_decision_limit_fails_closed():
    graph = ObservationGraph()

    for invalid in (0, 26):
        try:
            build_red_team_decisions([], graph, limit=invalid)
        except ValueError as exc:
            assert "between 1 and 25" in str(exc)
        else:
            raise AssertionError("invalid decision limit should fail")
