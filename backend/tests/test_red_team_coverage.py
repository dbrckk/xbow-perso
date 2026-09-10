from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.red_team_coverage import build_red_team_coverage, campaign_red_team_coverage
from app.storage import Storage


def test_red_team_coverage_reports_gaps_without_executing_actions():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=secret",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("endpoint:e",),
        )
    )

    result = build_red_team_coverage(graph)

    assert result["read_only"] is True
    assert result["safe_validation_only"] is True
    assert result["summary"]["observed_endpoints"] == 1
    assert result["summary"]["reviewed_endpoints"] == 0
    assert result["summary"]["observed_findings"] == 1
    assert result["summary"]["independently_validated_findings"] == 0
    assert "authorization_review_pending" in result["gaps"]
    assert "input_review_pending" in result["gaps"]
    assert "independent_validation_pending" in result["gaps"]
    assert "secret" not in str(result)


def test_endpoint_review_credit_requires_recorded_review_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=1",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    before = build_red_team_coverage(graph)

    graph.add(
        Observation(
            "evidence:review",
            "evidence",
            "review-recorded",
            "review-agent",
            parent_ids=("endpoint:e",),
            metadata={"review_type": "authorization_surface_review"},
        )
    )
    after = build_red_team_coverage(graph)

    assert before["summary"]["reviewed_endpoints"] == 0
    assert after["summary"]["reviewed_endpoints"] == 1
    assert after["score"] > before["score"]


def test_red_team_coverage_improves_after_independent_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("asset:a",)))
    before = build_red_team_coverage(graph)

    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:x1",
            "evidence",
            "artifact-reference",
            "independent-validator",
            parent_ids=("validation:v1",),
        )
    )
    after = build_red_team_coverage(graph)

    assert after["score"] > before["score"]
    assert after["summary"]["independently_validated_findings"] == 1
    assert after["summary"]["complete_evidence_chains"] == 1
    assert "independent_validation_pending" not in after["gaps"]
    assert "evidence_chain_incomplete" not in after["gaps"]


def test_red_team_coverage_route_is_exposed_and_reads_durable_graph(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="coverage-1",
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
    store.put_observation(campaign.id, Observation("asset:a", "asset", "example.test", "recon").to_dict())

    result = campaign_red_team_coverage(campaign.id)

    assert "/api/campaigns/{campaign_id}/red-team-coverage" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["safe_validation_only"] is True
