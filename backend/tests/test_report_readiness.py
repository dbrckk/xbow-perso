from types import SimpleNamespace

from app.main import app
from app.observation_graph import Observation, ObservationGraph
from app.report_readiness import build_report_readiness


def _finding(finding_id: str, status: str = "validation_required"):
    return SimpleNamespace(
        id=finding_id,
        title=f"Finding {finding_id}",
        status=status,
        severity="high",
        asset="example.test",
        endpoint=f"https://example.test/{finding_id}",
        cwe="CWE-200",
        cvss=7.5,
        summary="Observed issue",
        impact="Security impact",
        remediation="Apply a fix",
        reproduction_steps=["Reproduce safely"],
        validated_by="independent-validator" if status == "confirmed" else None,
    )


def _base_graph() -> ObservationGraph:
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
    return graph


def test_report_readiness_blocks_unvalidated_finding():
    item = build_report_readiness([_finding("f1")], _base_graph())[0]

    assert item.ready_for_human_review is False
    assert "finding_not_confirmed" in item.blockers
    assert "missing_independent_validation" in item.blockers
    assert "incomplete_evidence_chain" in item.blockers


def test_report_readiness_observed_validation_without_evidence_stays_blocked():
    graph = _base_graph()
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )

    item = build_report_readiness([_finding("f1", "confirmed")], graph)[0]

    assert item.independent_validation_observed is True
    assert item.evidence_backed_independent_validation is False
    assert item.consensus_level == "none"
    assert item.ready_for_human_review is False
    assert "missing_evidence_backed_independent_validation" in item.blockers
    assert "incomplete_evidence_chain" in item.blockers
    assert item.score == 0.40


def test_report_readiness_requires_complete_independent_evidence():
    graph = _base_graph()
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
        )
    )

    item = build_report_readiness([_finding("f1", "confirmed")], graph)[0]

    assert item.score == 1.0
    assert item.independent_validation_observed is True
    assert item.evidence_backed_independent_validation is True
    assert item.consensus_level == "single_evidence_backed_validator"
    assert item.ready_for_human_review is True
    assert item.blockers == ()


def test_report_readiness_duplicate_requires_review():
    findings = [_finding("f1", "confirmed"), _finding("f2", "confirmed")]
    findings[1].endpoint = findings[0].endpoint
    graph = ObservationGraph()

    items = build_report_readiness(findings, graph)

    assert all(item.duplicate_candidate for item in items)
    assert all("duplicate_review_required" in item.blockers for item in items)
    assert all(item.ready_for_human_review is False for item in items)


def test_report_readiness_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/report-readiness" in app.openapi()["paths"]


def test_report_readiness_distinguishes_human_review_from_submission_completeness():
    finding = _finding("f1", "confirmed")
    finding.cvss = None
    finding.impact = ""
    finding.remediation = ""
    graph = _base_graph()
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

    item = build_report_readiness([finding], graph)[0]

    assert item.ready_for_human_review is True
    assert item.submission_ready is False
    assert "impact_present" in item.metadata_blockers
    assert "remediation_present" in item.metadata_blockers
    assert "cvss_present" in item.metadata_blockers


def test_report_readiness_rejects_invalid_cwe_shape_for_submission():
    finding = _finding("f1", "confirmed")
    finding.cwe = "CWE-0"
    graph = ObservationGraph()

    item = build_report_readiness([finding], graph)[0]

    assert item.submission_ready is False
    assert item.metadata_checks["cwe_valid"] is False
    assert "cwe_valid" in item.metadata_blockers


def test_review_queue_and_report_readiness_routes_are_registered():
    paths = app.openapi()["paths"]

    assert "/api/campaigns/{campaign_id}/review-queue" in paths
    assert "/api/campaigns/{campaign_id}/report-readiness" in paths
