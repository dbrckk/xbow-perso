from types import SimpleNamespace

from app.finding_lifecycle import build_finding_lifecycle
from app.main import app
from app.observation_graph import Observation, ObservationGraph


def _finding(finding_id: str, status: str):
    return SimpleNamespace(
        id=finding_id,
        status=status,
        title="fixture",
        severity="medium",
        asset="example.test",
        endpoint=f"https://example.test/{finding_id}",
        cwe="CWE-200",
    )


def test_candidate_recommends_validation_without_execution_authority():
    item = build_finding_lifecycle([_finding("f1", "candidate")], ObservationGraph())[0]

    assert item.recommended_state == "validation_required"
    assert item.transition_allowed is True
    assert item.human_decision_required is False
    assert item.graph_observed is False
    assert item.evidence_chain_integrity_ok is False


def test_validation_required_blocks_until_independent_complete_evidence():
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

    item = build_finding_lifecycle([_finding("f1", "validation_required")], graph)[0]

    assert item.recommended_state == "human_confirm_or_reject"
    assert item.transition_allowed is False
    assert item.human_decision_required is True
    assert item.graph_observed is True
    assert item.evidence_chain_integrity_ok is True
    assert "independent_validation" in item.prerequisites
    assert "complete_evidence_chain" in item.prerequisites


def test_confirmed_finding_with_complete_chain_is_ready_for_human_report_review():
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

    item = build_finding_lifecycle([_finding("f1", "confirmed")], graph)[0]

    assert item.recommended_state == "human_report_review"
    assert item.transition_allowed is True
    assert item.prerequisites == ()
    assert item.human_decision_required is True
    assert item.graph_observed is True
    assert item.evidence_chain_integrity_ok is True


def test_rejected_finding_is_terminal():
    item = build_finding_lifecycle([_finding("f1", "rejected")], ObservationGraph())[0]

    assert item.recommended_state == "terminal"
    assert item.transition_allowed is False
    assert item.graph_observed is False
    assert item.evidence_chain_integrity_ok is False


def test_finding_lifecycle_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/finding-lifecycle" in app.openapi()["paths"]
