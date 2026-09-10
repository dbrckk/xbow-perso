from app.evidence_chain import build_evidence_chains, campaign_evidence_chains
from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def test_incomplete_chain_reports_missing_support():
    graph = ObservationGraph()
    graph.add(Observation("finding:f1", "finding", "f1", "scanner"))

    chains = build_evidence_chains(graph)

    assert len(chains) == 1
    chain = chains[0]
    assert chain.complete is False
    assert chain.independent_validation_observed is False
    assert chain.source_count == 1
    assert chain.dangling_parent_ids == ()
    assert chain.cycle_detected is False
    assert chain.issues == (
        "missing_upstream_context",
        "missing_validation",
        "missing_independent_observed_validation",
        "missing_evidence",
        "low_source_diversity",
    )


def test_complete_chain_correlates_ancestors_validation_and_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/api",
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

    chain = build_evidence_chains(graph)[0]

    assert chain.complete is True
    assert chain.ancestor_ids == ("asset:a", "endpoint:e")
    assert chain.validation_ids == ("validation:v1",)
    assert chain.evidence_ids == ("evidence:x1",)
    assert chain.source_count == 3
    assert chain.dangling_parent_ids == ()
    assert chain.cycle_detected is False
    assert chain.independent_validation_observed is True
    assert chain.issues == ()


def test_self_validation_keeps_chain_incomplete():
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
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "scanner",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:x1",
            "evidence",
            "artifact-reference",
            "scanner",
            parent_ids=("validation:v1",),
        )
    )

    chain = build_evidence_chains(graph)[0]

    assert chain.complete is False
    assert chain.source_count == 1
    assert chain.issues == (
        "missing_independent_observed_validation",
        "low_source_diversity",
    )


def test_dangling_parent_reference_is_reported():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("endpoint:missing",),
        )
    )

    chain = build_evidence_chains(graph)[0]

    assert chain.dangling_parent_ids == ("endpoint:missing",)
    assert "dangling_parent_reference" in chain.issues
    assert chain.complete is False


def test_ancestry_cycle_is_detected_without_recursion_loop():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "asset:a",
            "asset",
            "example.test",
            "recon",
            parent_ids=("endpoint:e",),
        )
    )
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/api",
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

    chain = build_evidence_chains(graph)[0]

    assert chain.cycle_detected is True
    assert "ancestry_cycle" in chain.issues
    assert chain.complete is False


def test_evidence_chain_route_is_exposed_and_read_only(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="chain-1",
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
        Observation("finding:f1", "finding", "f1", "scanner").to_dict(),
    )

    result = campaign_evidence_chains(campaign.id)

    assert "/api/campaigns/{campaign_id}/evidence-chains" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["summary"] == {
        "total": 1,
        "complete": 0,
        "incomplete": 1,
        "cycles": 0,
        "dangling_parent_references": 0,
        "low_source_diversity": 1,
    }
