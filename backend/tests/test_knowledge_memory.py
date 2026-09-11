from types import SimpleNamespace

from app.knowledge_memory import (
    build_knowledge_snapshot,
    decision_history,
    rank_findings,
    rank_findings_explainable,
    review_severity_bonus,
    severity_weight,
    temporal_need,
)
from app.observation_graph import Observation, ObservationGraph


def _finding_graph():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    return graph


def test_confidence_increases_with_observed_validation_and_evidence():
    graph = _finding_graph()

    baseline = build_knowledge_snapshot(graph)
    assert baseline.finding_confidence[0].score == 0.35

    graph.add(Observation("v1", "validation", "observed", "validator", parent_ids=("f1",)))
    validated = build_knowledge_snapshot(graph)
    assert validated.finding_confidence[0].score == 0.75

    graph.add(
        Observation(
            "e1",
            "evidence",
            "artifact-1",
            "validator",
            parent_ids=("v1",),
            metadata={"artifact_kind": "validation"},
        )
    )
    evidenced = build_knowledge_snapshot(graph)
    assert evidenced.finding_confidence[0].score == 1.0
    assert evidenced.finding_confidence[0].validation_count == 1
    assert evidenced.finding_confidence[0].evidence_count == 1


def test_dry_run_and_error_do_not_masquerade_as_strong_validation():
    dry_run_graph = _finding_graph()
    dry_run_graph.add(Observation("v-dry", "validation", "dry_run", "validator", parent_ids=("f1",)))
    dry_run_graph.add(
        Observation(
            "e-dry",
            "evidence",
            "artifact-dry",
            "validator",
            parent_ids=("v-dry",),
            metadata={"artifact_kind": "validation"},
        )
    )
    dry_run_confidence = build_knowledge_snapshot(dry_run_graph).finding_confidence[0]
    assert dry_run_confidence.score == 0.40
    assert dry_run_confidence.validation_count == 1
    assert dry_run_confidence.evidence_count == 0

    error_graph = _finding_graph()
    error_graph.add(Observation("v-error", "validation", "error", "validator", parent_ids=("f1",)))
    error_graph.add(
        Observation(
            "e-error",
            "evidence",
            "artifact-error",
            "validator",
            parent_ids=("v-error",),
            metadata={"artifact_kind": "validation"},
        )
    )
    error_confidence = build_knowledge_snapshot(error_graph).finding_confidence[0]
    assert error_confidence.score == 0.35
    assert error_confidence.validation_count == 0
    assert error_confidence.evidence_count == 0


def test_unknown_validation_outcome_fails_closed():
    graph = _finding_graph()
    graph.add(Observation("v1", "validation", "mystery", "validator", parent_ids=("f1",)))

    confidence = build_knowledge_snapshot(graph).finding_confidence[0]
    assert confidence.score == 0.35
    assert confidence.validation_count == 0
    assert confidence.evidence_count == 0


def test_self_validation_receives_no_confidence_credit():
    graph = _finding_graph()
    graph.add(Observation("v1", "validation", "observed", "scanner", parent_ids=("f1",)))
    graph.add(
        Observation(
            "e1",
            "evidence",
            "artifact-1",
            "scanner",
            parent_ids=("v1",),
            metadata={"artifact_kind": "validation"},
        )
    )

    confidence = build_knowledge_snapshot(graph).finding_confidence[0]

    assert confidence.score == 0.35
    assert confidence.validation_count == 0
    assert confidence.evidence_count == 0


def test_rank_findings_prioritizes_severity():
    graph = ObservationGraph()
    findings = [
        SimpleNamespace(id="low", severity="low"),
        SimpleNamespace(id="critical", severity="critical"),
        SimpleNamespace(id="medium", severity="medium"),
    ]

    ranked = rank_findings(findings, graph)

    assert [item.finding_id for item in ranked] == ["critical", "medium", "low"]


def test_rank_findings_uses_evidence_gap_as_tiebreaker():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(Observation("finding:f2", "finding", "f2", "scanner", parent_ids=("a1",)))
    graph.add(Observation("v1", "validation", "observed", "validator", parent_ids=("finding:f1",)))

    findings = [
        SimpleNamespace(id="f1", severity="high"),
        SimpleNamespace(id="f2", severity="high"),
    ]
    ranked = rank_findings(findings, graph)

    assert ranked[0].finding_id == "f2"
    assert ranked[0].confidence < ranked[1].confidence


def test_decision_history_reads_only_planner_memory_records():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "d1",
            "evidence",
            "scan",
            "orchestrator",
            metadata={
                "memory_type": "planner_decision",
                "action": "scan",
                "agent": "analysis-agent",
                "reason": "inventory ready",
                "priority": 80,
                "graph_fingerprint": "abc",
            },
        )
    )
    graph.add(Observation("e1", "evidence", "artifact", "validator"))

    history = decision_history(graph)
    assert len(history) == 1
    assert history[0]["action"] == "scan"
    assert history[0]["agent"] == "analysis-agent"


def test_explainable_ranking_combines_severity_evidence_and_stability():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("finding:critical", "finding", "critical", "scanner", parent_ids=("a1",)))
    graph.add(Observation("finding:low", "finding", "low", "scanner", parent_ids=("a1",)))
    findings = [
        SimpleNamespace(id="critical", severity="critical"),
        SimpleNamespace(id="low", severity="low"),
    ]

    ranked = rank_findings_explainable(
        findings,
        graph,
        stability={
            "critical": {"stability": "contradictory"},
            "low": {"stability": "stable"},
        },
    )

    assert [item["finding_id"] for item in ranked] == ["critical", "low"]
    assert ranked[0]["components"]["severity"] == 0.55
    assert ranked[0]["components"]["temporal_need"] == 0.15
    assert ranked[0]["components"]["total"] == ranked[0]["score"]
    assert ranked[0]["advisory_only"] is True


def test_explainable_ranking_rewards_evidence_gap_for_equal_severity():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(Observation("finding:f2", "finding", "f2", "scanner", parent_ids=("a1",)))
    graph.add(Observation("v1", "validation", "observed", "validator", parent_ids=("finding:f1",)))
    findings = [
        SimpleNamespace(id="f1", severity="high"),
        SimpleNamespace(id="f2", severity="high"),
    ]

    ranked = rank_findings_explainable(findings, graph)

    assert ranked[0]["finding_id"] == "f2"
    assert ranked[0]["components"]["evidence_gap"] > ranked[1]["components"]["evidence_gap"]


def test_explainable_ranking_unknown_severity_fails_closed():
    graph = ObservationGraph()
    findings = [SimpleNamespace(id="f1", severity="unexpected")]

    ranked = rank_findings_explainable(findings, graph)

    assert ranked[0]["components"]["severity"] == 0.0
    assert ranked[0]["stability"] == "unknown"


def test_shared_scoring_tables_are_monotonic_and_fail_closed():
    severities = ["info", "low", "medium", "high", "critical"]

    severity_values = [severity_weight(item) for item in severities]
    review_values = [review_severity_bonus(item) for item in severities]

    assert severity_values == sorted(severity_values)
    assert review_values == sorted(review_values)
    assert severity_weight("unexpected") == 0.0
    assert review_severity_bonus("unexpected") == 0.0


def test_temporal_need_prioritizes_contradiction_over_stability():
    assert temporal_need("contradictory") > temporal_need("evolving")
    assert temporal_need("evolving") > temporal_need("fresh")
    assert temporal_need("fresh") > temporal_need("stable")
    assert temporal_need("unexpected") == 0.25


def test_classic_and_explainable_rankings_share_severity_order():
    graph = ObservationGraph()
    findings = [
        SimpleNamespace(id="info", severity="info"),
        SimpleNamespace(id="low", severity="low"),
        SimpleNamespace(id="medium", severity="medium"),
        SimpleNamespace(id="high", severity="high"),
        SimpleNamespace(id="critical", severity="critical"),
    ]

    classic = rank_findings(findings, graph)
    explainable = rank_findings_explainable(
        findings,
        graph,
        stability={item.id: {"stability": "stable"} for item in findings},
    )

    assert [item.finding_id for item in classic] == [
        "critical",
        "high",
        "medium",
        "low",
        "info",
    ]
    assert [item["finding_id"] for item in explainable] == [
        "critical",
        "high",
        "medium",
        "low",
        "info",
    ]
