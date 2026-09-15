from types import SimpleNamespace

from app.observation_graph import Observation, ObservationGraph
from app.reporting_governance import (
    assess_report_artifact_freshness,
    build_reporting_governance_snapshot,
    verify_reporting_governance_snapshot,
)


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
    assert len(snapshot.governance_fingerprint) == 64
    assert verify_reporting_governance_snapshot(snapshot)["valid"] is True

    summary = snapshot.summary()
    assert summary["findings"] == 1
    assert summary["provenance_complete"] == 1
    assert summary["provenance_fingerprint"] == snapshot.provenance_fingerprint
    assert summary["governance_fingerprint"] == snapshot.governance_fingerprint
    assert summary["read_only"] is True
    assert summary["advisory_only"] is True


def test_reporting_governance_snapshot_is_deterministic():
    first = build_reporting_governance_snapshot([_finding()], _graph())
    second = build_reporting_governance_snapshot([_finding()], _graph())

    assert first.provenance_fingerprint == second.provenance_fingerprint
    assert first.governance_fingerprint == second.governance_fingerprint
    assert first.provenance[0].fingerprint == second.provenance[0].fingerprint


def test_reporting_governance_snapshot_verifier_detects_tampering():
    snapshot = build_reporting_governance_snapshot([_finding()], _graph())
    tampered = snapshot.__class__(
        readiness=snapshot.readiness,
        provenance=snapshot.provenance,
        quality_gates=snapshot.quality_gates,
        provenance_fingerprint="0" * 64,
        governance_fingerprint=snapshot.governance_fingerprint,
    )

    verification = verify_reporting_governance_snapshot(tampered)

    assert verification["valid"] is False
    assert (
        verification["expected_fingerprint"]
        != verification["computed_fingerprint"]
    )



def test_report_artifact_freshness_matches_current_governance():
    snapshot = build_reporting_governance_snapshot([_finding()], _graph())

    result = assess_report_artifact_freshness(
        artifact_id="report-1",
        generated_governance_fingerprint=snapshot.governance_fingerprint,
        generated_provenance_fingerprint=snapshot.provenance_fingerprint,
        current=snapshot,
    )

    assert result["fresh"] is True
    assert result["stale"] is False
    assert result["stale_reasons"] == []
    assert result["read_only"] is True
    assert result["automatic_mutation"] is False


def test_report_artifact_freshness_explains_governance_and_provenance_drift():
    snapshot = build_reporting_governance_snapshot([_finding()], _graph())

    result = assess_report_artifact_freshness(
        artifact_id="report-1",
        generated_governance_fingerprint="0" * 64,
        generated_provenance_fingerprint="1" * 64,
        current=snapshot,
    )

    assert result["fresh"] is False
    assert result["stale"] is True
    assert result["stale_reasons"] == [
        "reporting_governance_changed",
        "report_provenance_changed",
    ]
