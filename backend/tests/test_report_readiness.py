from types import SimpleNamespace

from app.main import app
from app.observation_graph import Observation, ObservationGraph
from app.report_readiness import build_report_readiness


def _finding(finding_id: str, status: str = "validation_required"):
    return SimpleNamespace(
        id=finding_id,
        status=status,
        severity="high",
        asset="example.test",
        endpoint=f"https://example.test/{finding_id}",
        cwe="CWE-200",
    )


def test_report_readiness_blocks_unvalidated_finding():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("asset:a",),
        )
    )

    item = build_report_readiness([_finding("f1")], graph)[0]

    assert item.ready_for_human_review is False
    assert "finding_not_confirmed" in item.blockers
    assert "missing_independent_validation" in item.blockers
    assert "incomplete_evidence_chain" in item.blockers


def test_report_readiness_requires_complete_independent_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
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
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:e1",
            "evidence",
            "artifact-reference",
            "independent-validator",
            parent_ids=("validation:v1",),
        )
    )

    item = build_report_readiness([_finding("f1", "confirmed")], graph)[0]

    assert item.score == 1.0
    assert item.ready_for_human_review is True
    assert item.blockers == ()


def test_report_readiness_duplicate_requires_review():
    findings = [_finding("f1", "confirmed"), _finding("f2", "confirmed")]
    findings[1].endpoint = findings[0].endpoint
    graph = ObservationGraph()

    items = build_report_readiness(findings, graph)

    assert all(item.duplicate_candidate for item in items)
    assert all("duplicate_review_required" in item.blockers for item in items)
    assert all(item.ready_for_human_review is False for item in items)


def test_report_readiness_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/report-readiness" in app.openapi()["paths"]
