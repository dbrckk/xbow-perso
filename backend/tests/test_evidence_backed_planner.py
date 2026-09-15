from types import SimpleNamespace

from app.observation_graph import AdaptivePlanner, Observation, ObservationGraph


def _campaign(status="validation_required"):
    return SimpleNamespace(
        target=SimpleNamespace(
            primary_url="https://example.test",
            rules=SimpleNamespace(automated_scanning=True),
        ),
        findings=[SimpleNamespace(id="f1", status=status)],
    )


def _observed_graph(*, with_evidence: bool) -> ObservationGraph:
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://example.test/api",
            "crawler",
            parent_ids=("a1",),
        )
    )
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "candidate",
            "scanner",
            parent_ids=("e1",),
        )
    )
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "validator",
            parent_ids=("finding:f1",),
        )
    )
    if with_evidence:
        graph.add(
            Observation(
                "evidence:v1",
                "evidence",
                "validation-artifact",
                "validator",
                parent_ids=("validation:v1",),
            )
        )
    return graph


def test_planner_fails_closed_when_observed_validation_lacks_attached_evidence():
    action = AdaptivePlanner().plan(_campaign(), _observed_graph(with_evidence=False))[0]

    assert action.kind == "stop"
    assert "lacks attached evidence" in action.reason


def test_planner_allows_resolution_gate_after_evidence_backed_validation():
    action = AdaptivePlanner().plan(_campaign(), _observed_graph(with_evidence=True))[0]

    assert action.kind == "stop"
    assert "explicit confirmation or rejection" in action.reason


def test_planner_allows_report_phase_only_after_evidence_backed_resolution():
    action = AdaptivePlanner().plan(
        _campaign(status="confirmed"),
        _observed_graph(with_evidence=True),
    )[0]

    assert action.kind == "report"
