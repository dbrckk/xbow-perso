from types import SimpleNamespace

from app.observation_graph import ObservationGraph
from app.report_readiness import build_report_readiness


def _finding(*, severity: str, cwe: str, cvss: float):
    return SimpleNamespace(
        id="f1",
        title="metadata fixture",
        status="confirmed",
        severity=severity,
        asset="https://example.test",
        endpoint="/fixture",
        cwe=cwe,
        cvss=cvss,
        summary="summary",
        impact="impact",
        remediation="remediation",
        reproduction_steps=["step"],
        validated_by="validator",
    )


def test_report_readiness_exposes_canonical_metadata():
    item = build_report_readiness(
        [_finding(severity="high", cwe=" cwe-200 ", cvss=7.5)],
        ObservationGraph(),
    )[0]

    assert item.canonical_cwe == "CWE-200"
    assert item.cvss_rating == "high"
    assert item.severity_cvss_consistent is True
    assert item.metadata_checks["cwe_valid"] is True
    assert item.metadata_checks["cvss_present"] is True
    assert item.metadata_checks["severity_cvss_consistent"] is True


def test_report_readiness_flags_cvss_severity_mismatch():
    item = build_report_readiness(
        [_finding(severity="medium", cwe="CWE-79", cvss=9.1)],
        ObservationGraph(),
    )[0]

    assert item.cvss_rating == "critical"
    assert item.severity_cvss_consistent is False
    assert "severity_cvss_consistent" in item.metadata_blockers
    assert item.submission_ready is False
