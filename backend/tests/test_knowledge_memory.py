from app.knowledge_memory import build_knowledge_snapshot, decision_history
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
