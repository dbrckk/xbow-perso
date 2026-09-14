from types import SimpleNamespace

from app.observation_graph import Observation, ObservationGraph
from app.report_quality import build_report_quality_gates, summarize_report_quality
from app.report_readiness import build_report_readiness


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


def _validated_graph() -> ObservationGraph:
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
                "artifact_kind": "validation",
                "artifact_sha256": "a" * 64,
            },
        )
    )
    return graph


def test_report_quality_gate_is_advisory_and_submission_safe():
    readiness = build_report_readiness([_finding()], _validated_graph())
    gates = build_report_quality_gates(readiness)
    summary = summarize_report_quality(gates)

    assert len(gates) == 1
    assert gates[0].human_review_ready is True
    assert gates[0].checks["evidence_backed_validation"] is True
    assert gates[0].checks["metadata_complete"] is True
    assert summary["human_approval_required"] is True
    assert summary["automatic_submission"] is False
    assert summary["read_only"] is True


def test_report_quality_gate_downgrades_incomplete_metadata():
    finding = _finding()
    finding.cvss = None
    finding.remediation = ""

    readiness = build_report_readiness([finding], _validated_graph())
    gate = build_report_quality_gates(readiness)[0]

    assert gate.submission_ready is False
    assert gate.grade in {"C", "D"}
    assert "metadata_complete" in gate.blockers
    assert "cvss_present" in gate.blockers
    assert "remediation_present" in gate.blockers
