from types import SimpleNamespace

from app.observation_graph import Observation, ObservationGraph
from app.planner_advisory import (
    advisory_focus_fingerprint,
    build_advisory_planner_context,
    diff_advisory_focus_snapshots,
)


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


def test_advisory_focus_fingerprint_is_deterministic():
    advisory = {
        "focus": [
            {"rank": 1, "finding_id": "f1", "score": 0.9},
            {"rank": 2, "finding_id": "f2", "score": 0.7},
        ],
        "top_n": 2,
        "rationale": "ignored for identity",
    }

    first = advisory_focus_fingerprint(advisory)
    second = advisory_focus_fingerprint(dict(reversed(list(advisory.items()))))

    assert first == second
    assert len(first) == 20


def test_advisory_delta_detects_top_change_as_significant():
    previous = {
        "fingerprint": "old",
        "advisory": {
            "focus": [
                {"rank": 1, "finding_id": "f1"},
                {"rank": 2, "finding_id": "f2"},
            ]
        },
    }
    current = {
        "fingerprint": "new",
        "advisory": {
            "focus": [
                {"rank": 1, "finding_id": "f2"},
                {"rank": 2, "finding_id": "f1"},
            ]
        },
    }

    delta = diff_advisory_focus_snapshots(previous, current)

    assert delta["top_changed"] is True
    assert delta["previous_top_finding_id"] == "f1"
    assert delta["current_top_finding_id"] == "f2"
    assert delta["significant"] is True
    assert delta["changed"] is True


def test_advisory_delta_tracks_entries_exits_and_rank_changes():
    previous = {
        "fingerprint": "old",
        "advisory": {
            "focus": [
                {"rank": 1, "finding_id": "f1"},
                {"rank": 2, "finding_id": "f2"},
                {"rank": 3, "finding_id": "f3"},
            ]
        },
    }
    current = {
        "fingerprint": "new",
        "advisory": {
            "focus": [
                {"rank": 1, "finding_id": "f1"},
                {"rank": 2, "finding_id": "f3"},
                {"rank": 3, "finding_id": "f4"},
            ]
        },
    }

    delta = diff_advisory_focus_snapshots(previous, current)

    assert delta["entered"] == ["f4"]
    assert delta["exited"] == ["f2"]
    assert delta["rank_changes"] == [
        {"finding_id": "f3", "from_rank": 3, "to_rank": 2, "delta": 1}
    ]
    assert delta["changed"] is True


def test_advisory_delta_is_empty_for_equivalent_focus():
    snapshot = {
        "fingerprint": "same",
        "advisory": {
            "focus": [
                {"rank": 1, "finding_id": "f1"},
                {"rank": 2, "finding_id": "f2"},
            ]
        },
    }

    delta = diff_advisory_focus_snapshots(snapshot, snapshot)

    assert delta["changed"] is False
    assert delta["significant"] is False
    assert delta["significance_score"] == 0.0
