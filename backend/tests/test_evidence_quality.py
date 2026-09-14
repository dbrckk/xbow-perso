from app.evidence_quality import build_evidence_quality, campaign_evidence_quality
from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def _base_graph() -> ObservationGraph:
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner-a",
            parent_ids=("asset:a",),
        )
    )
    return graph


def test_unvalidated_finding_has_low_evidence_quality():
    item = build_evidence_quality(_base_graph())[0]

    assert item.finding_id == "f1"
    assert item.grade == "low"
    assert item.score == 0.15
    assert item.independent_validation is False
    assert item.artifact_backed is False
    assert item.chain_integrity is True
    assert "missing_independent_observed_validation" in item.issues
    assert "missing_linked_evidence" in item.issues


def test_independent_artifact_backed_multi_source_evidence_is_high_quality():
    graph = _base_graph()
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "validator-b",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:e1",
            "evidence",
            "validation-artifact",
            "validator-c",
            parent_ids=("validation:v1",),
            metadata={
                "artifact_id": "artifact-1",
                "artifact_kind": "validation",
            },
        )
    )

    item = build_evidence_quality(graph)[0]

    assert item.score == 1.0
    assert item.grade == "high"
    assert item.independent_validation is True
    assert item.artifact_backed is True
    assert item.source_count == 3
    assert item.chain_integrity is True
    assert item.corroborated is True
    assert item.issues == ()


def test_plain_linked_evidence_does_not_receive_artifact_credit():
    graph = _base_graph()
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "validator-b",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:e1",
            "evidence",
            "plain-reference",
            "validator-b",
            parent_ids=("validation:v1",),
        )
    )

    item = build_evidence_quality(graph)[0]

    assert item.grade == "medium"
    assert item.artifact_backed is False
    assert item.components["artifact_backing"] == 0.10
    assert "evidence_not_artifact_backed" in item.issues


def test_corrupt_chain_loses_integrity_credit():
    graph = _base_graph()
    graph._items["asset:a"] = Observation(
        "asset:a",
        "asset",
        "example.test",
        "recon",
        parent_ids=("missing:parent",),
    )

    item = build_evidence_quality(graph)[0]

    assert item.chain_integrity is False
    assert item.components["chain_integrity"] == 0.0
    assert "incomplete_or_corrupt_chain" in item.issues


def test_evidence_quality_route_is_exposed(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="evidence-quality-1",
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
    store.put_observation(
        campaign.id,
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner-a",
            parent_ids=("asset:a",),
        ).to_dict(),
    )

    result = campaign_evidence_quality(campaign.id)

    assert "/api/campaigns/{campaign_id}/evidence-quality" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["advisory_only"] is True
    assert result["summary"]["low"] == 1
