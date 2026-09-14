from types import SimpleNamespace

from app.finding_cluster_consensus import build_cluster_consensus
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


def _graph_for(ids):
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    for fid in ids:
        graph.add(
            Observation(
                f"finding:{fid}",
                "finding",
                fid,
                "scanner-a",
                parent_ids=("asset:a",),
            )
        )
        graph.add(
            Observation(
                f"validation:{fid}",
                "validation",
                "observed",
                f"validator-{fid}",
                parent_ids=(f"finding:{fid}",),
            )
        )
        graph.add(
            Observation(
                f"evidence:{fid}",
                "evidence",
                "artifact-reference",
                f"evidence-{fid}",
                parent_ids=(f"validation:{fid}",),
                metadata={
                    "artifact_id": f"artifact-{fid}",
                    "artifact_kind": "validation",
                    "artifact_sha256": "a" * 64,
                },
            )
        )
    return graph


def test_cluster_consensus_ready_only_when_all_members_are_ready():
    findings = [
        _finding("f1", "https://example.test/a?id=1"),
        _finding("f2", "https://example.test/a?id=2"),
    ]
    snapshots = [
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.95, "status": "supported"},
                {"finding_id": "f2", "confidence": 0.95, "status": "supported"},
            ],
        }
    ]

    result = build_cluster_consensus(
        findings,
        _graph_for(["f1", "f2"]),
        hypothesis_snapshots=snapshots,
    )

    assert len(result) == 1
    cluster = result[0]
    assert cluster.status == "report_review_ready"
    assert cluster.report_ready_count == 2
    assert cluster.blockers == ()
    assert cluster.min_readiness >= 0.80


def test_cluster_consensus_does_not_promote_mixed_cluster():
    findings = [
        _finding("f1", "https://example.test/a?id=1"),
        _finding("f2", "https://example.test/a?id=2"),
    ]
    graph = _graph_for(["f1", "f2"])
    # Remove support for f2 so the cluster is intentionally mixed.
    graph._items.pop("validation:f2")
    graph._items.pop("evidence:f2")
    snapshots = [
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.95, "status": "supported"},
                {"finding_id": "f2", "confidence": 0.35, "status": "unvalidated"},
            ],
        }
    ]

    cluster = build_cluster_consensus(
        findings,
        graph,
        hypothesis_snapshots=snapshots,
    )[0]

    assert cluster.status != "report_review_ready"
    assert cluster.needs_validation_count == 1
    assert "cluster_contains_unvalidated_finding" in cluster.blockers
    assert "cluster_not_uniformly_report_ready" in cluster.blockers


def test_cluster_consensus_blocks_on_any_contradictory_member():
    findings = [
        _finding("f1", "https://example.test/a?id=1"),
        _finding("f2", "https://example.test/a?id=2"),
    ]
    snapshots = [
        {
            "graph_fingerprint": "c",
            "created_at": "2026-09-14T09:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.75, "status": "partially_supported"},
                {"finding_id": "f2", "confidence": 0.95, "status": "supported"},
            ],
        },
        {
            "graph_fingerprint": "b",
            "created_at": "2026-09-14T08:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.95, "status": "supported"},
                {"finding_id": "f2", "confidence": 0.95, "status": "supported"},
            ],
        },
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.35, "status": "unvalidated"},
                {"finding_id": "f2", "confidence": 0.95, "status": "supported"},
            ],
        },
    ]

    cluster = build_cluster_consensus(
        findings,
        _graph_for(["f1", "f2"]),
        hypothesis_snapshots=snapshots,
    )[0]

    assert cluster.status == "blocked"
    assert cluster.contradictory_count == 1
    assert "cluster_contains_contradictory_history" in cluster.blockers


def test_cluster_consensus_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/finding-cluster-consensus" in app.openapi()["paths"]
