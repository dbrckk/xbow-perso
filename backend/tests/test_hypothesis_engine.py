from app.hypothesis_engine import build_hypotheses, campaign_hypotheses
from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def test_hypotheses_are_bounded_and_deterministic():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://example.test/account?id=1",
            "recon",
            parent_ids=("a1",),
        )
    )
    graph.add(Observation("t1", "technology", "framework-x", "recon", parent_ids=("a1",)))

    first = build_hypotheses(graph, limit=2)
    second = build_hypotheses(graph, limit=2)

    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert len(first) == 2
    assert first[0].kind == "authorization_surface_review"
    assert all(item.next_action in {"scan", "validate", "stop"} for item in first)
    assert all(item.read_only is True for item in first)


def test_hypothesis_redacts_query_values_and_keeps_parameter_names():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://EXAMPLE.test:443/account?token=super-secret&id=42#private",
            "recon",
            parent_ids=("a1",),
        )
    )

    hypotheses = build_hypotheses(graph)
    payload = [item.to_dict() for item in hypotheses]

    assert {item["target"] for item in payload} == {"https://example.test/account"}
    assert all(item["parameter_names"] == ["id", "token"] for item in payload)
    assert "super-secret" not in str(payload)
    assert "42" not in str(payload)
    assert "private" not in str(payload)


def test_unvalidated_finding_gets_high_priority_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))

    hypotheses = build_hypotheses(graph)

    assert hypotheses[0].kind == "validation_gap"
    assert hypotheses[0].confidence == 0.90
    assert hypotheses[0].next_action == "validate"


def test_observed_independent_validation_closes_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )

    assert build_hypotheses(graph) == []


def test_self_validation_does_not_close_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "scanner",
            parent_ids=("finding:f1",),
        )
    )

    hypotheses = build_hypotheses(graph)
    assert hypotheses[0].kind == "validation_gap"


def test_hypothesis_route_is_exposed_and_reads_durable_graph(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="hypothesis-1",
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
    store.put_observation(campaign.id, Observation("a1", "asset", "example.test", "recon").to_dict())
    store.put_observation(
        campaign.id,
        Observation(
            "e1",
            "endpoint",
            "https://example.test/profile?session=do-not-leak",
            "recon",
            parent_ids=("a1",),
        ).to_dict(),
    )

    result = campaign_hypotheses(campaign.id)

    assert "/api/campaigns/{campaign_id}/hypotheses" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["safe_validation_only"] is True
    assert result["summary"]["total"] == 2
    assert result["summary"]["by_kind"] == {
        "authorization_surface_review": 1,
        "input_surface_review": 1,
    }
    assert "do-not-leak" not in str(result)


def test_limit_fails_closed_outside_bounds():
    graph = ObservationGraph()

    for invalid in (0, 101):
        try:
            build_hypotheses(graph, limit=invalid)
        except ValueError as exc:
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("invalid limit should fail")
