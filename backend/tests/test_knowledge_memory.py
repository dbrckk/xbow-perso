from types import SimpleNamespace

from app.knowledge_memory import build_knowledge_snapshot, decision_history, rank_findings
from app.observation_graph import Observation, ObservationGraph


def test_confidence_increases_with_validation_and_evidence():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(Observation("f1", "finding", "f1", "scanner", parent_ids=("a1",)))

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
