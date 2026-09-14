from types import SimpleNamespace

from app.finding_readiness import build_finding_readiness
from app.main import app
from app.observation_graph import Observation, ObservationGraph


def _finding(finding_id="f1", severity="high"):
    return SimpleNamespace(id=finding_id, severity=severity)


def _strong_graph():
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
            metadata={
                "artifact_id": "artifact-1",
                "artifact_kind": "validation",
                "artifact_sha256": "a" * 64,
            },
        )
    )
    return graph


def test_readiness_requires_validation_for_weak_evidence():
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

    item = build_finding_readiness([_finding()], graph)[0]

    assert item.readiness == "needs_validation"
    assert item.contradictory is False
    assert "insufficient_confidence" in item.blockers
    assert "insufficient_evidence_quality" in item.blockers
    assert "insufficient_independent_corroboration" in item.blockers


def test_readiness_can_be_report_review_ready_with_strong_independent_evidence():
    snapshots = [
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "f1",
                    "confidence": 0.95,
                    "status": "supported",
                }
            ],
        }
    ]

    item = build_finding_readiness(
        [_finding()],
        _strong_graph(),
        hypothesis_snapshots=snapshots,
    )[0]

    assert item.readiness == "report_review_ready"
    assert item.readiness_score >= 0.80
    assert item.blockers == ()
    assert item.evidence_quality == 1.0
    assert item.consensus_score >= 0.85


def test_contradictory_history_blocks_readiness_even_with_strong_evidence():
    snapshots = [
        {
            "graph_fingerprint": "c",
            "created_at": "2026-09-14T09:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "f1",
                    "confidence": 0.75,
                    "status": "partially_supported",
                }
            ],
        },
        {
            "graph_fingerprint": "b",
            "created_at": "2026-09-14T08:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "f1",
                    "confidence": 0.95,
                    "status": "supported",
                }
            ],
        },
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "f1",
                    "confidence": 0.35,
                    "status": "unvalidated",
                }
            ],
        },
    ]

    item = build_finding_readiness(
        [_finding()],
        _strong_graph(),
        hypothesis_snapshots=snapshots,
    )[0]

    assert item.readiness == "blocked"
    assert item.contradictory is True
    assert "contradictory_history" in item.blockers


def test_readiness_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/finding-readiness" in app.openapi()["paths"]
