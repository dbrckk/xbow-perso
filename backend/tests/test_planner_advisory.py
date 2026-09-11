from types import SimpleNamespace

from app.observation_graph import Observation, ObservationGraph
from app.planner_advisory import build_advisory_planner_context


def _campaign(findings):
    return SimpleNamespace(findings=findings)


def test_advisory_context_selects_highest_ranked_finding():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(Observation("finding:f2", "finding", "f2", "scanner", parent_ids=("a1",)))
    campaign = _campaign([
        SimpleNamespace(id="f1", severity="low"),
        SimpleNamespace(id="f2", severity="critical"),
    ])

    context = build_advisory_planner_context(campaign, graph)

    assert context["focus_finding_id"] == "f2"
    assert context["ranking"][0]["finding_id"] == "f2"
    assert context["read_only"] is True
    assert context["advisory_only"] is True


def test_advisory_context_uses_temporal_stability_in_focus_selection():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(Observation("finding:f2", "finding", "f2", "scanner", parent_ids=("a1",)))
    campaign = _campaign([
        SimpleNamespace(id="f1", severity="high"),
        SimpleNamespace(id="f2", severity="high"),
    ])

    context = build_advisory_planner_context(
        campaign,
        graph,
        stability={
            "f1": {"stability": "stable"},
            "f2": {"stability": "contradictory"},
        },
    )

    assert context["focus_finding_id"] == "f2"
    assert "stability=contradictory" in context["rationale"]


def test_advisory_context_handles_no_findings():
    context = build_advisory_planner_context(_campaign([]), ObservationGraph())

    assert context["focus_finding_id"] is None
    assert context["ranking"] == []
    assert "no findings" in context["rationale"]


def test_advisory_context_returns_bounded_top_n_focus():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    findings = []
    for index, severity in enumerate(("critical", "high", "medium", "low"), start=1):
        finding_id = f"f{index}"
        graph.add(
            Observation(
                f"finding:{finding_id}",
                "finding",
                finding_id,
                "scanner",
                parent_ids=("a1",),
            )
        )
        findings.append(SimpleNamespace(id=finding_id, severity=severity))

    context = build_advisory_planner_context(_campaign(findings), graph, top_n=2)

    assert context["focus_count"] == 2
    assert context["top_n"] == 2
    assert [item["rank"] for item in context["focus"]] == [1, 2]
    assert [item["finding_id"] for item in context["focus"]] == ["f1", "f2"]
    assert context["focus"][0]["components"]["total"] == context["focus"][0]["score"]


def test_advisory_context_rejects_unbounded_top_n():
    for invalid in (0, 11):
        try:
            build_advisory_planner_context(_campaign([]), ObservationGraph(), top_n=invalid)
        except ValueError as exc:
            assert "between 1 and 10" in str(exc)
        else:
            raise AssertionError("invalid top_n must fail closed")
