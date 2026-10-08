from app.coverage import build_coverage_guidance, build_evidence_coverage, prioritize_action_with_coverage
from app.main import app
from app.observation_graph import Observation, ObservationGraph, PlannedAction


def test_coverage_is_read_only_and_does_not_claim_unknown_completeness():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://example.test/",
            "recon:crawl",
            parent_ids=("a1",),
        )
    )

    result = build_evidence_coverage(graph, scope_checker=lambda _host: True)

    assert 0.0 <= result["score"] <= 1.0
    assert result["dimensions"]["scanner_execution"] == 0.0
    assert result["dimensions"]["independent_validation"] is None
    assert result["interpretation"] == "evidence_coverage_not_unknown_surface_completeness"
    assert result["read_only"] is True


def test_coverage_counts_scan_and_independent_validation():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://example.test/",
            "recon:crawl",
            parent_ids=("a1",),
        )
    )
    graph.add(
        Observation(
            "f1",
            "finding",
            "fixture",
            "nuclei",
            parent_ids=("a1",),
        )
    )
    graph.add(
        Observation(
            "scan1",
            "evidence",
            "completed",
            "nuclei",
            metadata={"phase": "scan", "status": "completed"},
        )
    )
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("f1",),
        )
    )

    result = build_evidence_coverage(graph, scope_checker=lambda _host: True)

    assert result["dimensions"]["scanner_execution"] == 1.0
    assert result["dimensions"]["independent_validation"] == 1.0
    assert result["evidence"]["scanner_sources"] == ["nuclei"]
    assert result["evidence"]["independently_observed_findings"] == 1


def test_coverage_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/coverage" in app.openapi()["paths"]


def test_coverage_guidance_is_advisory_only():
    guidance = build_coverage_guidance(
        {
            "score": 0.2,
            "dimensions": {
                "surface_discovery": 0.2,
                "scanner_execution": 0.0,
                "independent_validation": None,
            },
        }
    )

    assert guidance["focus"] == "surface_discovery"
    assert guidance["advisory_only"] is True
    assert guidance["may_unlock_actions"] is False
    assert guidance["interpretation"] == "evidence_guidance_not_security_assurance"


def test_coverage_guidance_prioritizes_validation_after_scan():
    guidance = build_coverage_guidance(
        {
            "score": 0.8,
            "dimensions": {
                "surface_discovery": 0.8,
                "scanner_execution": 1.0,
                "independent_validation": 0.5,
            },
        }
    )

    assert guidance["focus"] == "independent_validation"



def test_coverage_detects_diminishing_scan_returns_without_findings():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://example.test/",
            "recon:crawl",
            parent_ids=("a1",),
        )
    )
    graph.add(
        Observation(
            "form1",
            "form",
            "https://example.test/login",
            "browser",
            parent_ids=("a1",),
            metadata={"method": "POST", "input_names": ["username"]},
        )
    )
    graph.add(
        Observation(
            "tech1",
            "technology",
            "example-stack",
            "recon",
            parent_ids=("a1",),
        )
    )
    for index in range(4):
        graph.add(
            Observation(
                f"scan{index}",
                "evidence",
                "completed",
                "nuclei",
                metadata={"phase": "scan", "status": "completed"},
            )
        )

    coverage = build_evidence_coverage(graph, scope_checker=lambda _host: True)
    guidance = build_coverage_guidance(coverage)

    assert coverage["evidence"]["completed_scans"] == 4
    assert coverage["dimensions"]["marginal_scan_yield"] == 0.0
    assert coverage["dimensions"]["diminishing_returns"] >= 0.5
    assert guidance["focus"] == "surface_rotation"
    assert guidance["recommended_strategy"] == "rotate_to_underexplored_in_scope_surface"
    assert guidance["advisory_only"] is True
    assert guidance["may_unlock_actions"] is False


def test_diminishing_returns_does_not_override_needed_validation():
    coverage = {
        "score": 0.8,
        "dimensions": {
            "surface_discovery": 0.8,
            "scanner_execution": 1.0,
            "independent_validation": 0.5,
            "marginal_scan_yield": 0.1,
            "diminishing_returns": 1.0,
        },
    }

    guidance = build_coverage_guidance(coverage)

    assert guidance["focus"] == "independent_validation"



def test_low_yield_scan_deprioritization_preserves_kind_and_target():
    action = PlannedAction(
        kind="scan",
        target="https://example.test/",
        reason="scan selected",
        priority=80,
    )
    adjusted, signal = prioritize_action_with_coverage(
        action,
        {
            "focus": "surface_rotation",
            "diminishing_returns": 0.8,
        },
    )

    assert adjusted.kind == action.kind
    assert adjusted.target == action.target
    assert adjusted.priority < action.priority
    assert signal["applied"] is True
    assert signal["priority_delta"] < 0
    assert signal["action_kind_unchanged"] is True
    assert signal["target_unchanged"] is True


def test_coverage_priority_never_changes_non_scan_action():
    action = PlannedAction(
        kind="crawl",
        target="https://example.test/",
        reason="crawl selected",
        priority=50,
    )

    adjusted, signal = prioritize_action_with_coverage(
        action,
        {
            "focus": "surface_rotation",
            "diminishing_returns": 1.0,
        },
    )

    assert adjusted == action
    assert signal["applied"] is False


def test_completed_scan_duplicates_do_not_inflate_rotation_guidance():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:a",
            "endpoint",
            "https://example.test/",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    for index in range(4):
        graph.add(
            Observation(
                f"scan:duplicate:{index}",
                "evidence",
                "completed",
                "nuclei",
                parent_ids=("asset:a",),
                metadata={
                    "phase": "scan",
                    "status": "completed",
                    "job_id": "same-job",
                },
            )
        )

    coverage = build_evidence_coverage(
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert coverage["evidence"]["completed_scans"] == 1
    assert coverage["evidence"]["duplicate_scan_observations"] == 3
    assert coverage["evidence"]["untrusted_scan_observations"] == 0
    assert coverage["dimensions"]["diminishing_returns"] == 0.0
    assert build_coverage_guidance(coverage)["focus"] != "surface_rotation"


def test_only_in_scope_linked_scan_evidence_contributes_to_coverage():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "scan:other",
            "evidence",
            "completed",
            "nuclei",
            parent_ids=("asset:b",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "job-other",
            },
        )
    )
    graph.add(
        Observation(
            "scan:unlinked",
            "evidence",
            "completed",
            "nuclei",
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "job-unknown",
            },
        )
    )

    coverage = build_evidence_coverage(
        graph,
        scope_checker=lambda host: host == "example.test",
    )
    assert coverage["evidence"]["completed_scans"] == 0
    assert coverage["evidence"]["untrusted_scan_observations"] == 2
    assert coverage["dimensions"]["scanner_execution"] == 0.0

    graph.add(
        Observation(
            "scan:in-scope",
            "evidence",
            "completed",
            "nuclei",
            parent_ids=("asset:a",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "job-a",
            },
        )
    )
    updated = build_evidence_coverage(
        graph, scope_checker=lambda host: host == "example.test"
    )
    assert updated["evidence"]["completed_scans"] == 1
    assert updated["evidence"]["untrusted_scan_observations"] == 2
    assert updated["evidence"]["scanner_sources"] == ["nuclei"]


def test_single_asset_legacy_completed_scan_remains_compatible():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "scan:legacy",
            "evidence",
            "completed",
            "nuclei",
            metadata={"phase": "scan", "status": "completed"},
        )
    )

    coverage = build_evidence_coverage(
        graph,
        scope_checker=lambda host: host == "example.test",
    )
    assert coverage["evidence"]["completed_scans"] == 1
    assert coverage["evidence"]["untrusted_scan_observations"] == 0


def test_scan_with_conflicting_asset_ancestors_is_not_trusted():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "scan:both",
            "evidence",
            "completed",
            "nuclei",
            parent_ids=("asset:a", "asset:b"),
            metadata={"phase": "scan", "status": "completed", "job_id": "both"},
        )
    )

    coverage = build_evidence_coverage(
        graph,
        scope_checker=lambda host: host == "example.test",
    )
    assert coverage["evidence"]["completed_scans"] == 0
    assert coverage["evidence"]["untrusted_scan_observations"] == 1


def test_completed_scan_through_endpoint_ancestry_is_counted():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:a",
            "endpoint",
            "https://example.test/",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "scan:linked",
            "evidence",
            "completed",
            "nuclei",
            parent_ids=("endpoint:a",),
            metadata={"phase": "scan", "status": "completed", "job_id": "linked"},
        )
    )

    coverage = build_evidence_coverage(
        graph,
        scope_checker=lambda host: host == "example.test",
    )
    assert coverage["evidence"]["completed_scans"] == 1


def test_invalid_scan_job_identifiers_do_not_inflate_coverage():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    for index, job_id in enumerate(("", "bad\njob", 123, "x" * 129)):
        graph.add(
            Observation(
                f"scan:invalid:{index}",
                "evidence",
                "completed",
                "nuclei",
                parent_ids=("asset:a",),
                metadata={
                    "phase": "scan",
                    "status": "completed",
                    "job_id": job_id,
                },
            )
        )

    coverage = build_evidence_coverage(
        graph,
        scope_checker=lambda host: host == "example.test",
    )
    assert coverage["evidence"]["completed_scans"] == 0
    assert coverage["evidence"]["untrusted_scan_observations"] == 4
