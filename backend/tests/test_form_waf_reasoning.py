from app.hypothesis_engine import build_hypotheses
from app.observation_graph import Observation, ObservationGraph
from app.red_team_coverage import build_red_team_coverage
from app.review_queue import build_review_queue


def _graph() -> ObservationGraph:
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/login",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "form:login",
            "form",
            "https://example.test/login?csrf=secret",
            "browser",
            parent_ids=("endpoint:e",),
            metadata={"method": "POST", "input_names": ["password", "username"]},
        )
    )
    graph.add(
        Observation(
            "waf:edge",
            "waf",
            "edge-protection",
            "recon",
            parent_ids=("asset:a",),
            metadata={"confidence": 0.9},
        )
    )
    return graph


def test_forms_and_wafs_generate_safe_bounded_hypotheses():
    hypotheses = build_hypotheses(_graph())
    by_kind = {item.kind: item for item in hypotheses}

    assert by_kind["form_surface_review"].target == "https://example.test/login"
    assert by_kind["form_surface_review"].parameter_names == ("password", "username")
    assert by_kind["protection_surface_review"].target == "edge-protection"
    assert all(item.read_only is True for item in hypotheses)
    assert "secret" not in str([item.to_dict() for item in hypotheses])


def test_review_queue_prioritizes_form_and_protection_context():
    tasks = build_review_queue(_graph())
    kinds = {item.kind for item in tasks}

    assert "review_form_surface" in kinds
    assert "review_protection_surface" in kinds
    assert all(item.priority <= 1.0 for item in tasks)
    assert "secret" not in str([item.to_dict() for item in tasks])


def test_coverage_requires_recorded_form_and_waf_review_evidence():
    graph = _graph()
    before = build_red_team_coverage(graph)

    assert before["summary"]["observed_forms"] == 1
    assert before["summary"]["reviewed_forms"] == 0
    assert before["summary"]["observed_wafs"] == 1
    assert before["summary"]["reviewed_wafs"] == 0
    assert "form_review_pending" in before["gaps"]
    assert "protection_review_pending" in before["gaps"]

    graph.add(
        Observation(
            "evidence:form-review",
            "evidence",
            "review-recorded",
            "review-agent",
            parent_ids=("form:login",),
            metadata={"review_type": "form_surface_review"},
        )
    )
    graph.add(
        Observation(
            "evidence:waf-review",
            "evidence",
            "review-recorded",
            "review-agent",
            parent_ids=("waf:edge",),
            metadata={"review_type": "protection_surface_review"},
        )
    )
    after = build_red_team_coverage(graph)

    assert after["summary"]["reviewed_forms"] == 1
    assert after["summary"]["reviewed_wafs"] == 1
    assert after["score"] > before["score"]
