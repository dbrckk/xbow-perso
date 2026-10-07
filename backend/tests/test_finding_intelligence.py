from types import SimpleNamespace

from app.finding_intelligence import build_finding_intelligence
from app.kev_catalog import build_kev_catalog
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


def test_finding_intelligence_surfaces_public_duplicate_similarity_without_blocking():
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
        }
    ]

    result = build_finding_intelligence(
        findings,
        _graph(),
        public_reports=public_reports,
        program_handle="alpha",
    )

    duplicate = result["findings"][0]["public_duplicate_similarity"]
    assert duplicate["similarity_signal"] > 0.35
    assert duplicate["automatic_report_block"] is False
    assert result["findings"][0]["status"] == "validation_required"
    assert result["summary"]["high_public_similarity_findings"] == 1


def test_finding_intelligence_exposes_advisory_validation_priority_only():
    finding = _finding(
        "f1",
        "https://example.test/a?id=one",
        severity="critical",
    )
    finding.cve_ids = ["CVE-2026-12345"]
    finding.evidence = ["cve-id:CVE-2026-12345"]
    finding.discovered_by = "nuclei"

    result = build_finding_intelligence([finding], _graph())
    row = result["findings"][0]
    priority = row["validation_priority"]

    assert priority["automatic_execution_authorized"] is False
    assert priority["non_destructive_only"] is True
    assert priority["independent_validation_required"] is True
    assert priority["recommended_state"] in {
        "safe_active_validation",
        "passive_review",
        "defer_low_signal",
        "defer_duplicate_validation",
        "no_action",
    }


def test_finding_intelligence_exposes_cve_risk_context_without_confirmation():
    finding = _finding(
        "f1",
        "https://example.test/a?id=one",
        severity="critical",
    )
    finding.cve_ids = ["CVE-2026-12345"]
    finding.evidence = ["cve-id:CVE-2026-12345"]
    finding.cvss = 9.8
    finding.epss_score = 0.8
    finding.epss_percentile = 0.99
    finding.cpe = ["cpe:2.3:a:vendor:product:1.2.3:*:*:*:*:*:*:*"]
    finding.template_verified = True
    finding.tags = ["kev"]

    result = build_finding_intelligence([finding], _graph())
    row = result["findings"][0]
    risk = row["cve_risk_context"]

    assert risk["risk_band"] == "critical_priority"
    assert risk["scanner_tagged_kev"] is True
    assert risk["authoritative_kev_verified"] is False
    assert risk["exploitability_confirmed"] is False
    assert row["validation_priority"]["automatic_execution_authorized"] is False


def test_finding_intelligence_counts_verified_kev_candidates():
    finding = _finding(
        "f1",
        "https://example.test/a?id=one",
        severity="critical",
    )
    finding.cve_ids = ["CVE-2026-12345"]
    finding.evidence = ["cve-id:CVE-2026-12345"]
    finding.cvss = 9.8
    finding.tags = ["kev"]

    catalog = build_kev_catalog(
        {
            "catalogVersion": "fixture",
            "dateReleased": "2026-10-06",
            "count": 1,
            "vulnerabilities": [
                {
                    "cveID": "CVE-2026-12345",
                    "vendorProject": "Vendor",
                    "product": "Product",
                    "dateAdded": "2026-10-01",
                    "dueDate": "2026-10-20",
                    "knownRansomwareCampaignUse": "Unknown",
                }
            ],
        },
        source_verified=True,
    )

    result = build_finding_intelligence(
        [finding],
        _graph(),
        kev_catalog=catalog,
    )

    assert result["findings"][0]["cve_risk_context"][
        "authoritative_kev_verified"
    ] is True
    assert result["summary"]["authoritative_kev_candidates"] == 1
    assert result["findings"][0]["validation_priority"][
        "automatic_execution_authorized"
    ] is False


def test_finding_intelligence_exposes_bounded_cve_validation_plan():
    finding = _finding("f1", "https://example.test/a")
    finding.cve_ids = ["CVE-2026-12345"]
    finding.evidence = ["cve-id:CVE-2026-12345"]

    result = build_finding_intelligence([finding], _graph())

    plan = result["findings"][0]["cve_validation_plan"]
    assert plan["automatic_execution_authorized"] is False
    assert plan["destructive_testing_allowed"] is False
    assert plan["state_changing_validation_allowed"] is False
    assert plan["exploit_execution_allowed"] is False
    assert plan["independent_validation_required"] is True


def test_finding_intelligence_surfaces_reproducible_differential_quality():
    finding = _finding(
        "f1",
        "https://example.test/search?q=redacted",
        severity="critical",
    )
    finding.evidence = []
    finding.discovered_by = "scanner-a"

    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner-a",
            parent_ids=("asset:a",),
        )
    )
    for observation_id, source in (
        ("validation:one", "validator-a"),
        ("validation:two", "validator-b"),
    ):
        graph.add(
            Observation(
                observation_id,
                "validation",
                "observed",
                source,
                parent_ids=("finding:f1",),
                metadata={
                    "finding_id": "f1",
                    "differential_signal": "strong",
                    "differential_parameter": "q",
                    "differential_marker_reflected": True,
                    "differential_status_changed": False,
                    "differential_body_changed": True,
                },
            )
        )

    result = build_finding_intelligence([finding], graph)
    row = result["findings"][0]

    assert row["differential"]["signal"] == "strong"
    assert row["differential_quality"]["reproducible"] is True
    assert row["differential_quality"]["reproducibility_level"] == (
        "multi_source_repeated"
    )
    assert row["differential_quality"]["false_positive_risk"] == "low"
    assert result["summary"]["reproducible_differential_findings"] == 1
    assert result["summary"]["low_false_positive_differential_findings"] == 1
    assert result["summary"]["contradictory_differential_findings"] == 0


def test_finding_intelligence_surfaces_reproduced_repeat_outcome():
    finding = _finding(
        "f1",
        "https://example.test/search?q=redacted",
        severity="critical",
    )
    finding.evidence = []
    finding.discovered_by = "scanner-a"

    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner-a",
            parent_ids=("asset:a",),
        )
    )
    for observation_id, source in (
        ("validation:one", "validator-a"),
        ("validation:two", "validator-b"),
    ):
        graph.add(
            Observation(
                observation_id,
                "validation",
                "observed",
                source,
                parent_ids=("finding:f1",),
                metadata={
                    "finding_id": "f1",
                    "differential_signal": "strong",
                    "differential_parameter": "q",
                    "differential_marker_reflected": True,
                    "differential_status_changed": False,
                    "differential_body_changed": True,
                },
            )
        )

    result = build_finding_intelligence([finding], graph)
    outcome = result["findings"][0]["repeat_validation_outcome"]

    assert outcome["state"] == "reproduced_strong_signal"
    assert outcome["confidence"] == "high"
    assert outcome["repeat_budget_exhausted"] is True
    assert outcome["human_review_required"] is True
    assert outcome["exploitability_confirmed"] is False
    assert outcome["zero_day_claim"] is False
    assert result["summary"]["reproduced_repeat_signals"] == 1


def test_finding_intelligence_surfaces_contradictory_repeat_outcome():
    finding = _finding(
        "f1",
        "https://example.test/search?q=redacted",
        severity="critical",
    )
    finding.evidence = []
    finding.discovered_by = "scanner-a"

    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner-a",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "validation:strong",
            "validation",
            "observed",
            "validator-a",
            parent_ids=("finding:f1",),
            metadata={
                "finding_id": "f1",
                "differential_signal": "strong",
                "differential_parameter": "q",
                "differential_marker_reflected": True,
                "differential_status_changed": False,
                "differential_body_changed": True,
            },
        )
    )
    graph.add(
        Observation(
            "validation:weak",
            "validation",
            "observed",
            "validator-b",
            parent_ids=("finding:f1",),
            metadata={
                "finding_id": "f1",
                "differential_signal": "weak",
                "differential_parameter": "q",
                "differential_marker_reflected": False,
                "differential_status_changed": False,
                "differential_body_changed": True,
            },
        )
    )

    result = build_finding_intelligence([finding], graph)
    outcome = result["findings"][0]["repeat_validation_outcome"]

    assert outcome["state"] == "contradictory"
    assert outcome["human_review_required"] is True
    assert outcome["repeat_budget_exhausted"] is True
    assert outcome["exploitability_confirmed"] is False
    assert result["summary"]["contradictory_repeat_outcomes"] == 1


def test_conflicting_product_versions_downgrade_cve_verdict():
    finding = _finding(
        "f1",
        "https://example.test/a",
        severity="critical",
    )
    finding.title = "nginx request parsing issue"
    finding.cve_ids = ["CVE-2026-12345"]
    finding.evidence = ["cve-id:CVE-2026-12345"]
    finding.discovered_by = "nuclei"

    graph = _graph()
    graph.add(
        Observation(
            "tech:nginx-old",
            "technology",
            "nginx/1.24.0",
            "httpx",
            metadata={"confidence": 0.9},
        )
    )
    graph.add(
        Observation(
            "tech:nginx-new",
            "technology",
            "nginx/1.25.5",
            "wappalyzer",
            metadata={"confidence": 0.9},
        )
    )

    result = build_finding_intelligence([finding], graph)
    row = result["findings"][0]

    assert row["technology"]["ambiguity_reasons"] == [
        "conflicting_version_fingerprints",
        "single_source_version_evidence",
    ]
    assert row["cve_evidence_verdict"]["verdict"] == (
        "ambiguous_version_candidate"
    )
    assert row["cve_evidence_verdict"]["confidence"] == "low"
    assert row["cve_validation_plan"]["validation_mode"] == "passive_recheck"
    assert row["validation_priority"]["recommended_state"] == "passive_review"


def test_declared_cve_product_missing_from_observed_stack_downgrades_verdict():
    finding = _finding(
        "f1",
        "https://example.test/a",
        severity="critical",
    )
    finding.title = "generic parsing issue"
    finding.product = "apache"
    finding.cve_ids = ["CVE-2026-12345"]
    finding.evidence = ["cve-id:CVE-2026-12345"]
    finding.discovered_by = "nuclei"

    graph = _graph()
    graph.add(
        Observation(
            "tech:nginx-a",
            "technology",
            "nginx/1.24.0",
            "httpx",
            metadata={"confidence": 0.9},
        )
    )
    graph.add(
        Observation(
            "tech:nginx-b",
            "technology",
            "nginx 1.24.0",
            "wappalyzer",
            metadata={"confidence": 0.9},
        )
    )

    result = build_finding_intelligence([finding], graph)
    row = result["findings"][0]

    assert row["technology"]["ambiguity_reasons"] == [
        "declared_product_not_observed",
    ]
    assert row["cve_evidence_verdict"]["verdict"] == (
        "ambiguous_version_candidate"
    )
    assert row["cve_validation_plan"]["validation_mode"] == "passive_recheck"
    assert row["validation_priority"]["recommended_state"] == "passive_review"


def test_stale_version_fingerprint_downgrades_cve_verdict():
    finding = _finding(
        "f1",
        "https://example.test/a",
        severity="critical",
    )
    finding.title = "nginx request parsing issue"
    finding.product = "nginx"
    finding.cve_ids = ["CVE-2026-12345"]
    finding.evidence = ["cve-id:CVE-2026-12345"]
    finding.discovered_by = "nuclei"

    graph = _graph()
    graph.add(
        Observation(
            "tech:nginx-stale",
            "technology",
            "nginx/1.24.0",
            "httpx",
            metadata={
                "confidence": 0.95,
                "observed_at": "2026-08-01T00:00:00+00:00",
            },
        )
    )

    result = build_finding_intelligence([finding], graph)
    row = result["findings"][0]

    assert "stale_version_fingerprints" in row["technology"][
        "freshness_ambiguity_reasons"
    ]
    assert row["cve_evidence_verdict"]["verdict"] == (
        "ambiguous_version_candidate"
    )
    assert row["cve_validation_plan"]["validation_mode"] == "passive_recheck"
    assert row["validation_priority"]["recommended_state"] == "passive_review"


def test_mismatched_cpe_downgrades_cve_verdict_and_risk_context():
    finding = _finding(
        "f1",
        "https://example.test/a",
        severity="critical",
    )
    finding.title = "django request parsing issue"
    finding.product = "django"
    finding.cve_ids = ["CVE-2026-12345"]
    finding.evidence = ["cve-id:CVE-2026-12345"]
    finding.cpe = [
        "cpe:2.3:a:apache:http_server:2.4.62:*:*:*:*:*:*:*"
    ]
    finding.discovered_by = "nuclei"

    graph = _graph()
    graph.add(
        Observation(
            "tech:django",
            "technology",
            "django/5.1.2",
            "httpx",
            metadata={
                "confidence": 0.95,
                "observed_at": "2026-10-07T00:00:00+00:00",
            },
        )
    )

    result = build_finding_intelligence([finding], graph)
    row = result["findings"][0]

    assert row["cpe_consistency"]["cpe_supports_product_identity"] is False
    assert row["cpe_consistency"]["reasons"] == ["cpe_product_mismatch"]
    assert row["cve_evidence_verdict"]["verdict"] == (
        "ambiguous_version_candidate"
    )
    assert "cpe_untrusted" in row["cve_risk_context"]["reasons"]
    assert row["cve_validation_plan"]["validation_mode"] == "passive_recheck"
