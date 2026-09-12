from app.decision_audit import (
    next_audit_link,
    seal_decision_metadata,
    verify_decision_audit_chain,
)
from app.observation_graph import Observation, ObservationGraph


def _decision(seq, previous_hash, *, observation_id=None, action="scan"):
    observation_id = observation_id or f"d{seq}"
    metadata = seal_decision_metadata(
        observation_id,
        {
            "memory_type": "planner_decision",
            "action": action,
            "agent": "analysis-agent",
            "reason": f"reason-{seq}",
            "priority": 80,
            "graph_fingerprint": f"fp-{seq}",
            "audit_seq": seq,
            "previous_decision_hash": previous_hash,
        },
    )
    return Observation(
        observation_id,
        "evidence",
        action,
        "orchestrator",
        metadata=metadata,
    )


def test_decision_audit_chain_verifies_and_links():
    graph = ObservationGraph()
    first = _decision(1, None)
    graph.add(first)
    second = _decision(2, first.metadata["decision_hash"])
    graph.add(second)

    result = verify_decision_audit_chain(graph)

    assert result["valid"] is True
    assert result["checked"] == 2
    assert result["legacy_unsealed"] == []
    assert next_audit_link(graph) == (3, second.metadata["decision_hash"])


def test_decision_audit_chain_detects_rewrite():
    graph = ObservationGraph()
    first = _decision(1, None)
    graph.add(first)
    tampered = Observation(
        first.id,
        first.kind,
        first.value,
        first.source,
        metadata={**first.metadata, "reason": "tampered"},
    )
    graph = ObservationGraph()
    graph.add(tampered)

    result = verify_decision_audit_chain(graph)

    assert result["valid"] is False
    assert result["reason"] == "decision hash mismatch"


def test_decision_audit_chain_detects_sequence_gap():
    graph = ObservationGraph()
    graph.add(_decision(2, None))

    result = verify_decision_audit_chain(graph)

    assert result["valid"] is False
    assert result["reason"] == "decision audit sequence gap"


def test_decision_audit_chain_preserves_legacy_unsealed_entries():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "legacy",
            "evidence",
            "crawl",
            "orchestrator",
            metadata={
                "memory_type": "planner_decision",
                "action": "crawl",
                "agent": "recon-agent",
                "reason": "legacy",
                "priority": 80,
                "graph_fingerprint": "old",
            },
        )
    )

    result = verify_decision_audit_chain(graph)

    assert result["valid"] is True
    assert result["checked"] == 0
    assert result["legacy_unsealed"] == ["legacy"]


def test_signed_decision_fails_closed_without_key(monkeypatch):
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "fixture-secret")
    graph = ObservationGraph()
    graph.add(_decision(1, None))
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)

    result = verify_decision_audit_chain(graph)

    assert result["valid"] is False
    assert result["reason"] == "verification key unavailable"
