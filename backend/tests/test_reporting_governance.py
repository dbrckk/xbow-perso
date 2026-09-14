from types import SimpleNamespace

from app.observation_graph import Observation, ObservationGraph
from app.reporting_governance import build_reporting_governance_snapshot


def _finding():
    return SimpleNamespace(
        id="f1",
        title="Finding f1",
        status="confirmed",
        severity="high",
        asset="example.test",
        endpoint="https://example.test/f1",
        cwe="CWE-200",
        cvss=7.5,
        summary="Observed issue",
        impact="Security impact",
        remediation="Apply a fix",
        reproduction_steps=["Reproduce safely"],
        validated_by="independent-validator",
    )


def _graph() -> ObservationGraph:
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
            metadata={
                "artifact_id": "artifact-f1",
                "artifact_sha256": "a" * 64,
            },
        )
    )
    return graph


def test_reporting_governance_snapshot_is_consistent_and_read_only():
    snapshot = build_reporting_governance_snapshot([_finding()], _graph())

    assert len(snapshot.readiness) == 1
    assert len(snapshot.provenance) == 1
    assert len(snapshot.quality_gates) == 1
    assert snapshot.readiness[0].finding_id == "f1"
    assert snapshot.provenance[0].finding_id == "f1"
    assert snapshot.quality_gates[0].finding_id == "f1"
    assert snapshot.quality_gates[0].checks["provenance_complete"] is True
    assert snapshot.quality_gates[0].checks["provenance_verified"] is True
    assert len(snapshot.provenance_fingerprint) == 64

    summary = snapshot.summary()
    assert summary["findings"] == 1
    assert summary["provenance_complete"] == 1
    assert summary["provenance_fingerprint"] == snapshot.provenance_fingerprint
    assert summary["read_only"] is True
    assert summary["advisory_only"] is True


def test_reporting_governance_snapshot_is_deterministic():
    first = build_reporting_governance_snapshot([_finding()], _graph())
    second = build_reporting_governance_snapshot([_finding()], _graph())

    assert first.provenance_fingerprint == second.provenance_fingerprint
    assert first.provenance[0].fingerprint == second.provenance[0].fingerprint
