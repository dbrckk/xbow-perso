from types import SimpleNamespace

from app.campaign_review_state import build_campaign_review_state
from app.main import app
from app.observation_graph import Observation, ObservationGraph


def _finding(finding_id: str, status: str = "validation_required"):
    return SimpleNamespace(
        id=finding_id,
        status=status,
        title="fixture",
        severity="high",
        asset="example.test",
        endpoint=f"https://example.test/{finding_id}",
        cwe="CWE-200",
    )


def test_review_state_prioritizes_independent_validation():
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

    state = build_campaign_review_state([_finding("f1")], graph)

    assert state["next_focus"] == "independent_validation"
    assert state["ready_for_human_review"] == 0
    assert state["blocked_from_human_review"] == 1
    assert state["human_approval_required"] is True
    assert state["execution_authority"] is False


def test_review_state_surfaces_human_report_review_when_ready():
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

    state = build_campaign_review_state([_finding("f1", "confirmed")], graph)

    assert state["next_focus"] == "human_report_review"
    assert state["ready_for_human_review"] == 1
    assert state["ready_finding_ids"] == ["f1"]
    assert state["chain_integrity_failures"] == 0


def test_review_state_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/review-state" in app.openapi()["paths"]
