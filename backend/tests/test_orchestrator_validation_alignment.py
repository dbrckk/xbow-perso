from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.observation_graph import Observation, ObservationGraph
from app.orchestrator import _pending_findings


def _campaign():
    return Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            Finding(
                id="f1",
                title="candidate",
                severity="medium",
                asset="https://example.test",
                summary="fixture",
                discovered_by="scanner",
            )
        ],
    )


def _graph(validation_value: str, validation_source: str) -> ObservationGraph:
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(
        Observation(
            "v1",
            "validation",
            validation_value,
            validation_source,
            parent_ids=("finding:f1",),
        )
    )
    return graph


def test_dry_run_validation_does_not_remove_pending_finding():
    pending = _pending_findings(_campaign(), _graph("dry_run", "independent-validator"))
    assert [item.id for item in pending] == ["f1"]


def test_self_validation_does_not_remove_pending_finding():
    pending = _pending_findings(_campaign(), _graph("observed", "scanner"))
    assert [item.id for item in pending] == ["f1"]


def test_independent_observed_validation_removes_pending_finding():
    pending = _pending_findings(_campaign(), _graph("observed", "independent-validator"))
    assert pending == []
