from app.finding_consensus import build_finding_consensus
from app.main import app
from app.observation_graph import Observation, ObservationGraph


def _graph() -> ObservationGraph:
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner-a", parent_ids=("asset:a",)))
    return graph


def test_single_source_finding_is_not_corroborated():
    result = build_finding_consensus(_graph())

    assert len(result) == 1
    assert result[0].finding_id == "f1"
    assert result[0].source_count == 1
    assert result[0].independent_validator_count == 0
    assert result[0].evidence_source_count == 0
    assert result[0].corroborated is False
    assert result[0].score == 0.30


def test_independent_validation_and_evidence_raise_consensus():
    graph = _graph()
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
            "artifact-reference",
            "validator-c",
            parent_ids=("validation:v1",),
        )
    )

    result = build_finding_consensus(graph)[0]

    assert result.corroborated is True
    assert result.source_count == 3
    assert result.independent_validator_count == 1
    assert result.evidence_source_count == 1
    assert result.score == 0.85
    assert result.sources == ("scanner-a", "validator-b", "validator-c")


def test_self_validation_does_not_count_as_independent_consensus():
    graph = _graph()
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "scanner-a",
            parent_ids=("finding:f1",),
        )
    )

    result = build_finding_consensus(graph)[0]

    assert result.corroborated is False
    assert result.independent_validator_count == 0
    assert result.score == 0.30


def test_finding_consensus_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/finding-consensus" in app.openapi()["paths"]
