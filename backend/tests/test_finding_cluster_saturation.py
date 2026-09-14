from types import SimpleNamespace

from app.finding_cluster_saturation import build_cluster_saturation
from app.main import app
from app.observation_graph import Observation, ObservationGraph


def _finding(fid: str, endpoint: str):
    return SimpleNamespace(
        id=fid,
        severity="high",
        asset="https://example.test",
        endpoint=endpoint,
        cwe="CWE-79",
        title="Reflected script injection",
    )


def _base_graph():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    for fid in ("f1", "f2"):
        graph.add(
            Observation(
                f"finding:{fid}",
                "finding",
                fid,
                "scanner-a",
                parent_ids=("asset:a",),
            )
        )
    return graph


def test_cluster_saturation_reports_strong_representative_and_saved_validations():
    findings = [
        _finding("f1", "https://example.test/a?id=one"),
        _finding("f2", "https://example.test/a?id=two"),
    ]
    graph = _base_graph()
    graph.add(
        Observation(
            "validation:f1",
            "validation",
            "observed",
            "validator-b",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:f1",
            "evidence",
            "artifact-reference",
            "validator-c",
            parent_ids=("validation:f1",),
            metadata={
                "artifact_id": "artifact-f1",
                "artifact_kind": "validation",
                "artifact_sha256": "a" * 64,
            },
        )
    )

    item = build_cluster_saturation(findings, graph)[0]

    assert item.saturated is True
    assert item.representative_finding_id == "f1"
    assert item.validations_saved == 1
    assert item.cluster_confidence >= 0.90
    assert all(item.criteria.values())
    assert "saturates" in item.reason


def test_cluster_saturation_explains_missing_quality_requirements():
    findings = [
        _finding("f1", "https://example.test/a?id=one"),
        _finding("f2", "https://example.test/a?id=two"),
    ]
    graph = _base_graph()
    graph.add(
        Observation(
            "validation:f1",
            "validation",
            "observed",
            "validator-b",
            parent_ids=("finding:f1",),
        )
    )

    item = build_cluster_saturation(findings, graph)[0]

    assert item.saturated is False
    assert item.representative_finding_id == "f1"
    assert item.validations_saved == 0
    assert item.criteria["representative_independently_observed"] is True
    assert item.criteria["evidence_quality_high"] is False
    assert item.criteria["artifact_integrity_attested"] is False
    assert item.criteria["independently_corroborated"] is False


def test_cluster_saturation_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/finding-cluster-saturation" in app.openapi()["paths"]
