from types import SimpleNamespace

from app.finding_intelligence import build_finding_intelligence
from app.main import app
from app.observation_graph import Observation, ObservationGraph


def _finding(fid: str, endpoint: str, severity: str = "high"):
    return SimpleNamespace(
        id=fid,
        severity=severity,
        status="validation_required",
        asset="https://example.test",
        endpoint=endpoint,
        cwe="CWE-79",
        title="Reflected script injection",
    )


def _graph():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    for fid in ("f1", "f2"):
        graph.add(
            Observation(
                f"finding:{fid}",
                "finding",
                fid,
                "scanner-a",
                parent_ids=("asset:a",),
            )
        )
    graph.add(
        Observation(
            "validation:f1",
            "validation",
            "observed",
            "validator-b",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:f1",
            "evidence",
            "artifact-reference",
            "validator-c",
            parent_ids=("validation:f1",),
            metadata={
                "artifact_id": "artifact-f1",
                "artifact_kind": "validation",
                "artifact_sha256": "a" * 64,
            },
        )
    )
    return graph


def test_finding_intelligence_consolidates_member_and_cluster_views():
    findings = [
        _finding("f1", "https://example.test/a?id=one"),
        _finding("f2", "https://example.test/a?id=two"),
    ]
    snapshots = [
        {
            "graph_fingerprint": "stable-a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {"finding_id": "f1", "confidence": 0.95, "status": "supported"},
                {"finding_id": "f2", "confidence": 0.35, "status": "unvalidated"},
            ],
        }
    ]

    result = build_finding_intelligence(
        findings,
        _graph(),
        hypothesis_snapshots=snapshots,
    )

    assert result["summary"]["findings"] == 2
    assert result["summary"]["clusters"] == 1
    assert len(result["findings"]) == 2
    assert len(result["clusters"]) == 1

    by_id = {item["finding_id"]: item for item in result["findings"]}
    assert by_id["f1"]["cluster_id"] == by_id["f2"]["cluster_id"]
    assert by_id["f1"]["readiness"] is not None
    assert by_id["f1"]["triage"] is not None
    assert result["clusters"][0]["consensus"] is not None
    assert result["clusters"][0]["saturation"] is not None


def test_finding_intelligence_summary_reflects_cluster_saturation():
    findings = [
        _finding("f1", "https://example.test/a?id=one"),
        _finding("f2", "https://example.test/a?id=two"),
    ]

    result = build_finding_intelligence(findings, _graph())

    assert result["summary"]["saturated_clusters"] == 1
    assert result["summary"]["validations_saved"] == 1
    cluster = result["clusters"][0]
    assert cluster["saturation"]["saturated"] is True
    assert cluster["saturation"]["representative_finding_id"] == "f1"


def test_finding_intelligence_does_not_expose_query_values():
    findings = [
        _finding("f1", "https://example.test/a?token=one"),
        _finding("f2", "https://example.test/a?token=two"),
    ]

    result = build_finding_intelligence(findings, _graph())
    serialized = str(result)

    assert "token=one" not in serialized
    assert "token=two" not in serialized


def test_finding_intelligence_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/finding-intelligence" in app.openapi()["paths"]



def test_finding_intelligence_surfaces_public_duplicate_risk_without_blocking():
    findings = [_finding("f1", "https://example.test/graphql", severity="high")]
    findings[0].summary = "GraphQL authorization bypass exposes admin object"
    findings[0].cwe = "CWE-862"
    public_reports = [
        {
            "id": "pub-1",
            "title": "GraphQL authorization bypass exposes admin object",
            "summary": "Authorization bypass on admin object",
            "cwe": "CWE-862",
            "program_handle": "alpha",
            "url": "https://hackerone.com/reports/1",
            "severity": "high",
            "award_amount": 5000,
            "currency": "USD",
        }
    ]

    result = build_finding_intelligence(
        findings,
        _graph(),
        public_reports=public_reports,
        program_handle="alpha",
    )

    duplicate = result["findings"][0]["public_duplicate_risk"]
    assert duplicate["risk_score"] > 0.35
    assert duplicate["automatic_report_block"] is False
