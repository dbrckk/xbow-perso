from __future__ import annotations

from app.no_finding_recovery import build_no_finding_recovery
from app.observation_graph import Observation, ObservationGraph


def _graph(*, scans: int = 1, with_endpoint: bool = True):
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    if with_endpoint:
        graph.add(
            Observation(
                "endpoint:a",
                "endpoint",
                "https://example.test/account?id=1",
                "crawler",
                parent_ids=("asset:a",),
            )
        )
    for index in range(scans):
        graph.add(
            Observation(
                f"scan:{index}",
                "evidence",
                "scan-complete",
                "nuclei",
                metadata={
                    "phase": "scan",
                    "status": "completed",
                    "job_id": f"job-{index}",
                },
            )
        )
    return graph


def _feedback(graph, *, allowed=None, scope=None, **kwargs):
    return build_no_finding_recovery(
        graph,
        scope_checker=scope if scope is not None else lambda host: host == "example.test",
        available_task_kinds=allowed
        if allowed is not None
        else ("map_endpoints", "detect_technology", "map_forms", "browser_observe"),
        **kwargs,
    )


def test_negative_scan_shifts_focus_to_unobserved_in_scope_surfaces():
    result = _feedback(_graph())

    assert result.state == "recovery_advisory"
    assert result.completed_scan_count == 1
    assert result.in_scope_endpoint_count == 1
    assert result.uncovered_endpoint_count == 1
    assert result.recommended_task_kinds == (
        "map_forms", "detect_technology", "map_endpoints"
    )
    assert result.negative_result_proves_safe is False
    assert result.may_expand_scope is False
    assert result.may_increase_request_budget is False
    assert result.may_enable_exploitation is False
    assert result.may_change_execution_gate is False
    assert result.to_dict()["advisory_only"] is True


def test_repeated_completed_scans_rotate_instead_of_repeating_scan():
    result = _feedback(_graph(scans=4))

    assert result.completed_scan_count == 4
    assert any("rotate coverage" in reason for reason in result.reasons)
    assert "scan" not in result.recommended_task_kinds
    assert len(result.recommended_task_kinds) <= 3


def test_duplicate_observations_for_one_scan_job_do_not_inflate_yield():
    graph = _graph(scans=1)
    graph.add(
        Observation(
            "scan:duplicate",
            "evidence",
            "scan-complete",
            "nuclei",
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "job-0",
            },
        )
    )
    result = _feedback(graph)

    assert result.completed_scan_count == 1
    assert result.scanner_source_count == 1
    assert not any("repeated completed scans" in reason for reason in result.reasons)


def test_failed_scans_do_not_count_as_null_findings():
    graph = _graph(scans=0)
    graph.add(
        Observation(
            "scan:failure",
            "evidence",
            "scan-failed",
            "nuclei",
            metadata={"phase": "scan", "status": "failed"},
        )
    )
    result = _feedback(graph)

    assert result.state == "no_completed_scans"
    assert result.completed_scan_count == 0
    assert result.recommended_task_kinds == ()


def test_campaign_findings_disable_no_finding_recovery_even_without_graph_record():
    result = _feedback(_graph(), campaign_finding_count=1)

    assert result.state == "findings_present"
    assert result.finding_count == 1
    assert result.recommended_task_kinds == ()


def test_existing_graph_finding_disables_null_scan_recovery():
    graph = _graph()
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "possible-issue",
            "scanner",
            parent_ids=("asset:a",),
        )
    )
    assert _feedback(graph).state == "findings_present"


def test_out_of_scope_asset_cannot_trigger_recovery():
    graph = _graph()
    result = _feedback(graph, scope=lambda _host: False)

    assert result.state == "scope_unverified"
    assert result.in_scope_endpoint_count == 0
    assert result.recommended_task_kinds == ()


def test_missing_scope_checker_disables_recommendations():
    result = build_no_finding_recovery(
        _graph(),
        scope_checker=None,
        available_task_kinds=("map_forms",),
    )

    assert result.state == "scope_unverified"
    assert result.recommended_task_kinds == ()


def test_repeated_failed_worker_requires_review_not_retry():
    result = _feedback(
        _graph(),
        worker_outcomes={
            "by_job_kind": {
                "nuclei_scan": {
                    "completed": 0,
                    "failed": 2,
                    "requeued": 1,
                }
            }
        },
    )

    assert result.state == "execution_unstable"
    assert result.recommended_task_kinds == ()


def test_feedback_never_invents_task_kinds_or_expands_configured_set():
    result = _feedback(
        _graph(scans=4),
        allowed=("map_forms", "arbitrary_shell", "scanner_unknown"),
    )

    assert result.state == "recovery_advisory"
    assert result.recommended_task_kinds == ("map_forms",)


def test_unavailable_recovery_tasks_fail_closed():
    result = _feedback(_graph(), allowed=("browser_observe",))

    assert result.state == "no_supported_recovery_task"
    assert result.recommended_task_kinds == ()


def test_no_endpoints_prefers_existing_bounded_crawl():
    result = _feedback(_graph(with_endpoint=False), allowed=("crawl", "detect_technology"))

    assert result.state == "recovery_advisory"
    assert result.recommended_task_kinds == ("crawl",)


def test_scope_integrity_gap_prioritized_before_more_scanning():
    graph = _graph()
    graph.add(
        Observation(
            "endpoint:orphan",
            "endpoint",
            "https://example.test/api?x=1",
            "crawler",
        )
    )
    result = _feedback(graph)

    assert result.scope_integrity_issues == 1
    assert result.recommended_task_kinds[0] == "map_endpoints"
    assert "scan" not in result.recommended_task_kinds


def test_reviewed_forms_no_longer_count_as_review_gap():
    graph = _graph(scans=3)
    graph.add(
        Observation(
            "form:one",
            "form",
            "https://example.test/login",
            "browser",
            parent_ids=("asset:a",),
            metadata={"method": "POST", "input_names": ["email"]},
        )
    )
    graph.add(
        Observation(
            "review:form",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("form:one",),
            metadata={"review_type": "form_surface_review", "status": "completed"},
        )
    )
    result = _feedback(graph)

    assert result.in_scope_form_count == 1
    assert result.uncovered_form_count == 0


def test_feedback_rejects_negative_campaign_finding_count():
    import pytest

    with pytest.raises(ValueError, match="campaign_finding_count"):
        _feedback(_graph(), campaign_finding_count=-1)


def test_out_of_scope_technology_does_not_satisfy_authorized_inventory():
    graph = _graph()
    graph.add(
        Observation("asset:other", "asset", "other.test", "inventory")
    )
    graph.add(
        Observation(
            "technology:other",
            "technology",
            "nginx/1.24.0",
            "httpx",
            parent_ids=("asset:other",),
        )
    )

    result = _feedback(graph)

    assert result.missing_technology_context is True
    assert "detect_technology" in result.recommended_task_kinds


def test_orphan_form_does_not_close_authorized_form_inventory_gap():
    graph = _graph()
    graph.add(
        Observation(
            "form:orphan",
            "form",
            "https://example.test/login",
            "browser",
            metadata={"method": "POST", "input_names": ["login"]},
        )
    )

    result = _feedback(graph)

    assert result.in_scope_form_count == 0
    assert result.recommended_task_kinds[0] == "map_forms"


def test_out_of_scope_form_does_not_close_authorized_form_inventory_gap():
    graph = _graph()
    graph.add(
        Observation("asset:other", "asset", "other.test", "inventory")
    )
    graph.add(
        Observation(
            "form:other",
            "form",
            "https://other.test/login",
            "browser",
            parent_ids=("asset:other",),
        )
    )

    result = _feedback(graph)

    assert result.in_scope_form_count == 0
    assert "map_forms" in result.recommended_task_kinds


def test_browser_already_attempted_does_not_create_infinite_recovery_loop():
    graph = _graph(scans=4)
    graph.add(
        Observation(
            "form:one",
            "form",
            "https://example.test/login",
            "form-discovery",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "technology:one",
            "technology",
            "nginx/1.24.0",
            "httpx",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "review:endpoint",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:a",),
            metadata={"review_type": "authorization_surface_review", "status": "completed"},
        )
    )
    graph.add(
        Observation(
            "review:form",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("form:one",),
            metadata={"review_type": "form_surface_review", "status": "completed"},
        )
    )
    before = _feedback(graph, allowed=("browser_observe",))
    assert before.recommended_task_kinds == ("browser_observe",)

    graph.add(
        Observation(
            "review:browser",
            "evidence",
            "completed",
            "browser-agent",
            metadata={"task_kind": "browser_observe", "status": "completed"},
        )
    )
    after = _feedback(graph, allowed=("browser_observe",))
    assert after.state == "no_supported_recovery_task"
    assert after.recommended_task_kinds == ()
    assert any("no automatic repeat" in reason for reason in after.reasons)


def _completed_recon_evidence(
    graph: ObservationGraph,
    *,
    task_kind: str,
    asset_id: str = "asset:a",
    evidence_id: str | None = None,
    status: str = "completed",
) -> None:
    graph.add(
        Observation(
            evidence_id or f"recovery:{task_kind}",
            "evidence",
            "bounded-recon-complete",
            "recon-worker",
            parent_ids=(asset_id,),
            metadata={"task_kind": task_kind, "status": status},
        )
    )


def test_completed_in_scope_recovery_task_is_not_recommended_twice():
    graph = _graph()
    _completed_recon_evidence(graph, task_kind="map_forms")
    result = _feedback(graph)

    assert "map_forms" not in result.recommended_task_kinds
    assert result.exhausted_task_kinds == ("map_forms",)
    assert result.recommended_task_kinds == (
        "detect_technology",
        "map_endpoints",
    )
    assert result.to_dict()["exhausted_task_kinds"] == ["map_forms"]
    assert any("do not repeat" in reason for reason in result.reasons)


def test_completed_all_candidate_recovery_tasks_requires_review():
    graph = _graph()
    for kind in ("map_forms", "detect_technology", "map_endpoints"):
        _completed_recon_evidence(graph, task_kind=kind)

    result = _feedback(graph)
    assert result.state == "no_supported_recovery_task"
    assert result.recommended_task_kinds == ()
    assert result.exhausted_task_kinds == (
        "detect_technology",
        "map_endpoints",
        "map_forms",
    )
    assert result.may_change_execution_gate is False
    assert result.may_increase_request_budget is False


def test_out_of_scope_recon_completion_does_not_exhaust_in_scope_task():
    graph = _graph()
    graph.add(
        Observation("asset:other", "asset", "other.test", "inventory")
    )
    _completed_recon_evidence(
        graph,
        task_kind="map_forms",
        asset_id="asset:other",
    )
    result = _feedback(graph)

    assert "map_forms" in result.recommended_task_kinds
    assert result.exhausted_task_kinds == ()


def test_orphan_recon_completion_does_not_exhaust_task():
    graph = _graph()
    graph.add(
        Observation(
            "recovery:orphan",
            "evidence",
            "bounded-recon-complete",
            "recon-worker",
            metadata={"task_kind": "map_forms", "status": "completed"},
        )
    )
    assert "map_forms" in _feedback(graph).recommended_task_kinds


def test_failed_or_queued_recon_task_does_not_exhaust_option():
    graph = _graph()
    _completed_recon_evidence(
        graph,
        task_kind="map_forms",
        evidence_id="recovery:failed",
        status="failed",
    )
    _completed_recon_evidence(
        graph,
        task_kind="map_forms",
        evidence_id="recovery:queued",
        status="queued",
    )
    result = _feedback(graph)
    assert "map_forms" in result.recommended_task_kinds
    assert result.exhausted_task_kinds == ()


def test_completed_recovery_cannot_create_new_authority():
    graph = _graph()
    _completed_recon_evidence(graph, task_kind="map_forms")
    result = _feedback(
        graph,
        allowed=("map_forms", "arbitrary_shell"),
    )
    assert result.state == "no_supported_recovery_task"
    assert result.recommended_task_kinds == ()
    assert result.advisory_only is True
    assert result.may_expand_scope is False
    assert result.may_enable_exploitation is False


def test_recovery_targets_only_requested_host_in_multi_host_campaign():
    graph = _graph(scans=1)
    graph.add(
        Observation("asset:b", "asset", "other.test", "inventory")
    )
    graph.add(
        Observation(
            "endpoint:b",
            "endpoint",
            "https://other.test/api",
            "crawler",
            parent_ids=("asset:b",),
        )
    )
    graph.add(
        Observation(
            "form:b",
            "form",
            "https://other.test/login",
            "browser",
            parent_ids=("asset:b",),
        )
    )
    graph.add(
        Observation(
            "technology:b",
            "technology",
            "nginx/1.24.0",
            "httpx",
            parent_ids=("asset:b",),
        )
    )
    _completed_recon_evidence(
        graph,
        task_kind="map_forms",
        asset_id="asset:b",
        evidence_id="recovery:b",
    )
    graph.add(
        Observation(
            "scan:scoped-a",
            "evidence",
            "scan-complete",
            "nuclei",
            parent_ids=("asset:a",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "job-scoped-a",
            },
        )
    )

    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
    )

    assert result.in_scope_endpoint_count == 1
    assert result.in_scope_form_count == 0
    assert result.missing_technology_context is True
    assert "map_forms" in result.recommended_task_kinds
    assert "detect_technology" in result.recommended_task_kinds
    assert result.exhausted_task_kinds == ()


def test_recovery_rejects_other_authorized_host_as_target_inventory():
    graph = _graph(scans=1)
    result = _feedback(
        graph,
        target_host="other.test",
        scope=lambda host: host in {"example.test", "other.test"},
    )

    assert result.state == "scope_unverified"
    assert result.recommended_task_kinds == ()
    assert result.in_scope_endpoint_count == 0


def test_recovery_target_host_exhaustion_is_not_cross_host():
    graph = _graph(scans=1)
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    _completed_recon_evidence(
        graph,
        task_kind="map_forms",
        asset_id="asset:a",
    )
    graph.add(
        Observation(
            "scan:scoped-b",
            "evidence",
            "scan-complete",
            "nuclei",
            parent_ids=("asset:b",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "job-scoped-b",
            },
        )
    )

    result = _feedback(
        graph,
        target_host="other.test",
        scope=lambda host: host in {"example.test", "other.test"},
        allowed=("crawl", "map_forms"),
    )

    assert result.state == "recovery_advisory"
    assert result.recommended_task_kinds == ("crawl",)
    assert result.exhausted_task_kinds == ()


def test_recovery_target_host_cannot_be_empty():
    import pytest

    with pytest.raises(ValueError, match="target_host"):
        _feedback(_graph(), target_host="   ")


def test_recovery_scopes_untrusted_endpoint_count_to_target():
    graph = _graph(scans=1)
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "scan:scoped-a",
            "evidence",
            "scan-complete",
            "nuclei",
            parent_ids=("asset:a",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "job-a",
            },
        )
    )
    graph.add(
        Observation(
            "endpoint:orphan-b",
            "endpoint",
            "https://other.test/path",
            "crawler",
        )
    )

    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
    )

    assert result.scope_integrity_issues == 0
    assert "map_forms" in result.recommended_task_kinds


def test_unscoped_scan_is_not_misattributed_to_target_in_multi_host_campaign():
    graph = _graph(scans=1)
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
    )

    assert result.state == "no_completed_scans"
    assert result.completed_scan_count == 0
    assert result.recommended_task_kinds == ()


def test_scoped_scan_on_other_host_cannot_trigger_negative_target_feedback():
    graph = _graph(scans=0)
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "scan:other",
            "evidence",
            "scan-complete",
            "nuclei",
            parent_ids=("asset:b",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "other-job",
            },
        )
    )

    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
    )
    assert result.state == "no_completed_scans"
    assert result.completed_scan_count == 0
    assert result.scanner_source_count == 0


def test_legacy_unscoped_scan_remains_valid_for_single_observed_host():
    result = _feedback(_graph(scans=1), target_host="example.test")

    assert result.state == "recovery_advisory"
    assert result.completed_scan_count == 1
    assert result.recommended_task_kinds


def _fully_reviewed_target_graph(*, additional_host: bool) -> ObservationGraph:
    graph = _graph(scans=0)
    if additional_host:
        graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "form:a",
            "form",
            "https://example.test/login",
            "form-discovery",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "technology:a",
            "technology",
            "nginx/1.24.0",
            "httpx",
            parent_ids=("asset:a",),
        )
    )
    for index in range(4):
        graph.add(
            Observation(
                f"scan:scoped-{index}",
                "evidence",
                "scan-complete",
                "nuclei",
                parent_ids=("asset:a",),
                metadata={
                    "phase": "scan",
                    "status": "completed",
                    "job_id": f"job-scoped-{index}",
                },
            )
        )
    for kind, parent in (
        ("authorization_surface_review", "endpoint:a"),
        ("form_surface_review", "form:a"),
    ):
        graph.add(
            Observation(
                f"review:{kind}",
                "evidence",
                "reviewed",
                "analyst",
                parent_ids=(parent,),
                metadata={"review_type": kind, "status": "completed"},
            )
        )
    return graph


def test_single_host_legacy_browser_completion_prevents_recovery_loop():
    graph = _fully_reviewed_target_graph(additional_host=False)
    graph.add(
        Observation(
            "browser:legacy",
            "evidence",
            "completed",
            "browser-agent",
            metadata={
                "task_kind": "browser_observe",
                "status": "completed",
            },
        )
    )

    result = _feedback(
        graph,
        target_host="example.test",
        allowed=("browser_observe",),
    )
    assert result.state == "no_supported_recovery_task"
    assert result.completed_scan_count == 4
    assert result.recommended_task_kinds == ()


def test_other_host_browser_completion_cannot_exhaust_target():
    graph = _fully_reviewed_target_graph(additional_host=True)
    graph.add(
        Observation(
            "browser:other",
            "evidence",
            "completed",
            "browser-agent",
            parent_ids=("asset:b",),
            metadata={
                "task_kind": "browser_observe",
                "status": "completed",
            },
        )
    )
    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
        allowed=("browser_observe",),
        worker_outcomes={
            "by_job_kind": {
                "browser_flow": {"completed": 1}
            }
        },
    )

    assert result.state == "recovery_advisory"
    assert result.recommended_task_kinds == ("browser_observe",)
    assert result.exhausted_task_kinds == ()


def test_queued_endpoint_review_does_not_close_coverage_gap():
    graph = _graph()
    graph.add(
        Observation(
            "review:queued",
            "evidence",
            "review-queued",
            "analyst",
            parent_ids=("endpoint:a",),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "queued",
            },
        )
    )
    result = _feedback(graph)

    assert result.uncovered_endpoint_count == 1
    assert "map_endpoints" in result.recommended_task_kinds


def test_failed_form_review_does_not_close_coverage_gap():
    graph = _graph()
    graph.add(
        Observation(
            "form:a",
            "form",
            "https://example.test/login",
            "form-discovery",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "review:failed",
            "evidence",
            "review-failed",
            "analyst",
            parent_ids=("form:a",),
            metadata={
                "review_type": "form_surface_review",
                "status": "failed",
            },
        )
    )
    result = _feedback(graph)

    assert result.uncovered_form_count == 1
    assert "browser_observe" in result.recommended_task_kinds


def test_completed_scoped_review_closes_only_its_own_endpoint_gap():
    graph = _graph()
    graph.add(
        Observation(
            "endpoint:second",
            "endpoint",
            "https://example.test/profile",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "review:done",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:a",),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )
    result = _feedback(graph)

    assert result.uncovered_endpoint_count == 1
    assert "map_endpoints" in result.recommended_task_kinds


def test_review_without_terminal_status_cannot_claim_coverage():
    graph = _graph()
    graph.add(
        Observation(
            "review:unknown",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:a",),
            metadata={"review_type": "authorization_surface_review"},
        )
    )

    assert _feedback(graph).uncovered_endpoint_count == 1


def _unattributed_scanner_failures():
    return {
        "by_job_kind": {
            "nuclei_scan": {
                "completed": 0,
                "failed": 3,
                "requeued": 1,
            }
        }
    }


def test_global_worker_failures_do_not_block_different_target_recovery():
    graph = _graph(scans=0)
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "scan:for-a",
            "evidence",
            "scan-complete",
            "nuclei",
            parent_ids=("asset:a",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "scan-a",
            },
        )
    )
    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
        worker_outcomes=_unattributed_scanner_failures(),
    )

    assert result.state == "recovery_advisory"
    assert result.completed_scan_count == 1
    assert "map_forms" in result.recommended_task_kinds
    assert result.worker_health_attribution == "unattributed_multi_host"
    assert result.worker_instability_observed is True
    assert result.worker_instability_applied is False
    assert any("cannot be attributed" in reason for reason in result.reasons)
    assert result.may_expand_scope is False
    assert result.may_enable_exploitation is False
    assert result.to_dict()["worker_instability_applied"] is False


def test_global_worker_failures_cannot_create_missing_target_scan_evidence():
    graph = _graph(scans=0)
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
        worker_outcomes=_unattributed_scanner_failures(),
    )

    assert result.state == "no_completed_scans"
    assert result.recommended_task_kinds == ()
    assert result.worker_instability_applied is False


def test_single_observed_host_still_blocks_recovery_on_real_worker_failure():
    result = _feedback(
        _graph(),
        target_host="example.test",
        worker_outcomes=_unattributed_scanner_failures(),
    )

    assert result.state == "execution_unstable"
    assert result.recommended_task_kinds == ()
    assert result.worker_health_attribution == "single_observed_host"
    assert result.worker_instability_observed is True
    assert result.worker_instability_applied is True


def test_legacy_campaign_wide_health_retains_conservative_gate():
    result = _feedback(
        _graph(),
        worker_outcomes=_unattributed_scanner_failures(),
    )
    assert result.state == "execution_unstable"
    assert result.worker_health_attribution == "campaign_aggregate"
    assert result.worker_instability_applied is True


def test_healthy_multi_host_worker_summary_does_not_claim_attribution():
    graph = _graph(scans=0)
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "scan:for-a",
            "evidence",
            "scan-complete",
            "nuclei",
            parent_ids=("asset:a",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "scan-a",
            },
        )
    )
    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
        worker_outcomes={"by_job_kind": {}},
    )
    assert result.state == "recovery_advisory"
    assert result.worker_instability_observed is False
    assert result.worker_instability_applied is False
    assert result.worker_health_attribution == "unattributed_multi_host"
    assert not any("cannot be attributed" in reason for reason in result.reasons)


def _record_completed_scan(
    graph: ObservationGraph,
    *,
    observation_id: str,
    job_id: str,
    source: str,
    asset_id: str = "asset:a",
) -> None:
    graph.add(
        Observation(
            observation_id,
            "evidence",
            "scan-complete",
            source,
            parent_ids=(asset_id,),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": job_id,
            },
        )
    )


def test_conflicting_sources_for_same_scan_job_do_not_count_as_independent():
    graph = _graph(scans=0)
    _record_completed_scan(
        graph, observation_id="scan:one", job_id="shared", source="nuclei"
    )
    _record_completed_scan(
        graph, observation_id="scan:two", job_id="shared", source="strix"
    )

    result = _feedback(graph, target_host="example.test")
    assert result.completed_scan_count == 1
    assert result.scanner_source_count == 0
    assert result.ambiguous_scan_source_jobs == 1
    assert result.state == "scan_source_unverified"
    assert result.recommended_task_kinds == ()
    assert result.to_dict()["ambiguous_scan_source_jobs"] == 1
    assert result.negative_result_proves_safe is False


def test_identical_repeated_scanner_source_for_one_job_counts_once():
    graph = _graph(scans=0)
    _record_completed_scan(
        graph, observation_id="scan:one", job_id="shared", source="nuclei"
    )
    _record_completed_scan(
        graph, observation_id="scan:two", job_id="shared", source="nuclei"
    )

    result = _feedback(graph, target_host="example.test")
    assert result.completed_scan_count == 1
    assert result.scanner_source_count == 1
    assert result.ambiguous_scan_source_jobs == 0
    assert result.state == "recovery_advisory"


def test_distinct_jobs_with_same_source_do_not_inflate_source_diversity():
    graph = _graph(scans=0)
    _record_completed_scan(
        graph, observation_id="scan:one", job_id="job-1", source="nuclei"
    )
    _record_completed_scan(
        graph, observation_id="scan:two", job_id="job-2", source="nuclei"
    )

    result = _feedback(graph, target_host="example.test")
    assert result.completed_scan_count == 2
    assert result.scanner_source_count == 1
    assert result.ambiguous_scan_source_jobs == 0
    assert result.recommended_task_kinds


def test_ambiguous_scan_does_not_hide_separate_trusted_scan():
    graph = _graph(scans=0)
    _record_completed_scan(
        graph, observation_id="scan:one", job_id="shared", source="nuclei"
    )
    _record_completed_scan(
        graph, observation_id="scan:two", job_id="shared", source="strix"
    )
    _record_completed_scan(
        graph, observation_id="scan:three", job_id="separate", source="nuclei"
    )

    result = _feedback(graph, target_host="example.test")
    assert result.completed_scan_count == 2
    assert result.scanner_source_count == 1
    assert result.ambiguous_scan_source_jobs == 1
    assert result.state == "recovery_advisory"
    assert any("contradictory" in reason for reason in result.reasons)


def test_missing_scanner_source_requires_review_not_recovery_escalation():
    graph = _graph(scans=0)
    _record_completed_scan(
        graph, observation_id="scan:unknown", job_id="job-a", source=""
    )

    result = _feedback(graph, target_host="example.test")
    assert result.completed_scan_count == 1
    assert result.scanner_source_count == 0
    assert result.ambiguous_scan_source_jobs == 1
    assert result.state == "scan_source_unverified"
    assert result.recommended_task_kinds == ()
    assert result.may_enable_exploitation is False
    assert result.may_increase_request_budget is False


def test_blank_duplicate_source_cannot_be_hidden_by_named_reporter():
    graph = _graph(scans=0)
    _record_completed_scan(
        graph, observation_id="scan:good", job_id="job-1", source="nuclei"
    )
    _record_completed_scan(
        graph, observation_id="scan:blank", job_id="job-1", source=" "
    )
    result = _feedback(graph, target_host="example.test")

    assert result.completed_scan_count == 1
    assert result.scanner_source_count == 0
    assert result.ambiguous_scan_source_jobs == 1
    assert result.state == "scan_source_unverified"
    assert result.recommended_task_kinds == ()


def test_oversized_scan_job_id_is_not_trusted_as_independent_source():
    graph = _graph(scans=0)
    _record_completed_scan(
        graph, observation_id="scan:long", job_id="a" * 129, source="nuclei"
    )
    result = _feedback(graph, target_host="example.test")

    assert result.completed_scan_count == 1
    assert result.scanner_source_count == 0
    assert result.ambiguous_scan_source_jobs == 1
    assert result.state == "scan_source_unverified"
    assert result.may_increase_request_budget is False


def _record_timestamped_recovery(
    graph: ObservationGraph,
    *,
    kind: str = "map_forms",
    completed_at: str = "2026-09-01T00:00:00+00:00",
    task_id: str = "recovery:timed",
) -> None:
    graph.add(
        Observation(
            task_id,
            "evidence",
            "completed",
            "recon-worker",
            parent_ids=("asset:a",),
            metadata={
                "task_kind": kind,
                "status": "completed",
                "completed_at": completed_at,
            },
        )
    )


def test_new_target_endpoint_after_recovery_completion_reopens_bounded_task():
    graph = _graph()
    _record_timestamped_recovery(graph)
    graph.add(
        Observation(
            "endpoint:new",
            "endpoint",
            "https://example.test/new-form",
            "crawler",
            parent_ids=("asset:a",),
            metadata={"observed_at": "2026-09-02T00:00:00+00:00"},
        )
    )

    result = _feedback(graph, target_host="example.test")

    assert "map_forms" in result.recommended_task_kinds
    assert result.reopened_task_kinds == ("map_forms",)
    assert "map_forms" not in result.exhausted_task_kinds
    assert result.to_dict()["reopened_task_kinds"] == ["map_forms"]
    assert result.may_increase_request_budget is False
    assert result.may_enable_exploitation is False
    assert result.advisory_only is True


def test_old_target_observation_cannot_reopen_exhausted_recon():
    graph = _graph()
    _record_timestamped_recovery(graph)
    graph.add(
        Observation(
            "endpoint:old",
            "endpoint",
            "https://example.test/old",
            "crawler",
            parent_ids=("asset:a",),
            metadata={"observed_at": "2026-08-01T00:00:00Z"},
        )
    )

    result = _feedback(graph, target_host="example.test")

    assert "map_forms" not in result.recommended_task_kinds
    assert result.exhausted_task_kinds == ("map_forms",)
    assert result.reopened_task_kinds == ()


def test_missing_or_invalid_completion_timestamp_does_not_reopen_task():
    for completed_at in ("", "unparseable", "2026-09-01T00:00:00"):
        graph = _graph()
        _record_timestamped_recovery(graph, completed_at=completed_at)
        graph.add(
            Observation(
                "endpoint:new",
                "endpoint",
                "https://example.test/new",
                "crawler",
                parent_ids=("asset:a",),
                metadata={"observed_at": "2026-09-02T00:00:00+00:00"},
            )
        )

        result = _feedback(graph, target_host="example.test")
        assert result.reopened_task_kinds == ()
        assert "map_forms" in result.exhausted_task_kinds


def test_cross_host_or_orphan_observation_does_not_reopen_target_task():
    graph = _graph(scans=0)
    graph.add(Observation("asset:b", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "scan:scoped-a",
            "evidence",
            "completed",
            "nuclei",
            parent_ids=("asset:a",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "scoped-a-job",
            },
        )
    )
    _record_timestamped_recovery(graph)
    graph.add(
        Observation(
            "endpoint:other",
            "endpoint",
            "https://other.test/new",
            "crawler",
            parent_ids=("asset:b",),
            metadata={"observed_at": "2026-09-02T00:00:00+00:00"},
        )
    )
    graph.add(
        Observation(
            "endpoint:orphan",
            "endpoint",
            "https://example.test/unlinked",
            "legacy-import",
            metadata={"observed_at": "2026-09-03T00:00:00+00:00"},
        )
    )

    result = _feedback(
        graph,
        target_host="example.test",
        scope=lambda host: host in {"example.test", "other.test"},
    )

    assert result.reopened_task_kinds == ()
    assert "map_forms" in result.exhausted_task_kinds
    assert "map_forms" not in result.recommended_task_kinds


def test_later_recovery_completion_prevents_repeating_old_novelty():
    graph = _graph()
    _record_timestamped_recovery(graph, completed_at="2026-09-01T00:00:00Z")
    _record_timestamped_recovery(
        graph,
        completed_at="2026-09-04T00:00:00Z",
        task_id="recovery:latest",
    )
    graph.add(
        Observation(
            "endpoint:new",
            "endpoint",
            "https://example.test/new",
            "crawler",
            parent_ids=("asset:a",),
            metadata={"observed_at": "2026-09-02T00:00:00Z"},
        )
    )

    result = _feedback(graph, target_host="example.test")
    assert result.reopened_task_kinds == ()
    assert "map_forms" in result.exhausted_task_kinds


def _two_origin_graph() -> ObservationGraph:
    graph = ObservationGraph()
    for scheme in ("http", "https"):
        graph.add(
            Observation(
                f"asset:{scheme}",
                "asset",
                f"{scheme}://example.test",
                "inventory",
            )
        )
        graph.add(
            Observation(
                f"endpoint:{scheme}",
                "endpoint",
                f"{scheme}://example.test/account",
                "crawler",
                parent_ids=(f"asset:{scheme}",),
            )
        )
    return graph


def test_negative_scan_on_http_does_not_trigger_https_recovery():
    graph = _two_origin_graph()
    graph.add(
        Observation(
            "scan:http",
            "evidence",
            "completed",
            "nuclei",
            parent_ids=("asset:http",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "http-job",
            },
        )
    )
    result = _feedback(
        graph,
        target_url="https://example.test",
        allowed=("map_forms", "map_endpoints"),
    )
    assert result.state == "no_completed_scans"
    assert result.completed_scan_count == 0
    assert result.in_scope_endpoint_count == 1
    assert result.recommended_task_kinds == ()


def test_origin_scoped_scan_recovers_only_its_endpoint_inventory():
    graph = _two_origin_graph()
    graph.add(
        Observation(
            "scan:https",
            "evidence",
            "completed",
            "nuclei",
            parent_ids=("asset:https",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "https-job",
            },
        )
    )
    graph.add(
        Observation(
            "form:http",
            "form",
            "http://example.test/login",
            "browser",
            parent_ids=("asset:http",),
        )
    )
    graph.add(
        Observation(
            "technology:http",
            "technology",
            "nginx/1.24.0",
            "httpx",
            parent_ids=("asset:http",),
        )
    )
    result = _feedback(
        graph,
        target_url="https://example.test",
    )

    assert result.state == "recovery_advisory"
    assert result.completed_scan_count == 1
    assert result.in_scope_endpoint_count == 1
    assert result.in_scope_form_count == 0
    assert result.missing_technology_context is True
    assert "map_forms" in result.recommended_task_kinds
    assert "detect_technology" in result.recommended_task_kinds


def test_endpoint_linked_to_different_port_does_not_fill_target_gap():
    graph = ObservationGraph()
    graph.add(
        Observation("asset:other", "asset", "https://example.test:8443", "inventory")
    )
    graph.add(
        Observation("asset:target", "asset", "https://example.test:443", "inventory")
    )
    graph.add(
        Observation(
            "endpoint:wrong-ancestor",
            "endpoint",
            "https://example.test:443/account",
            "crawler",
            parent_ids=("asset:other",),
        )
    )
    graph.add(
        Observation(
            "scan:target",
            "evidence",
            "complete",
            "nuclei",
            parent_ids=("asset:target",),
            metadata={"phase": "scan", "status": "completed"},
        )
    )

    result = _feedback(
        graph,
        target_url="https://example.test",
        allowed=("crawl", "map_endpoints"),
    )
    assert result.state == "recovery_advisory"
    assert result.in_scope_endpoint_count == 0
    assert result.scope_integrity_issues >= 1
    assert "map_endpoints" in result.recommended_task_kinds


def test_legacy_unlinked_scan_requires_explicit_matching_asset_origin():
    legacy = _graph(scans=1)
    result = _feedback(legacy, target_url="https://example.test")
    assert result.state == "no_completed_scans"
    assert result.completed_scan_count == 0

    graph = ObservationGraph()
    graph.add(
        Observation("asset:https", "asset", "https://example.test", "inventory")
    )
    graph.add(
        Observation(
            "scan:unlinked",
            "evidence",
            "complete",
            "nuclei",
            metadata={"phase": "scan", "status": "completed"},
        )
    )
    compatible = _feedback(
        graph,
        target_url="https://example.test",
        allowed=("crawl",),
    )
    assert compatible.completed_scan_count == 1
    assert compatible.state == "recovery_advisory"


def test_invalid_or_mismatched_target_origin_is_rejected():
    import pytest

    for invalid in ("", "ftp://example.test", "https://user@example.test", "https://example.test:99999"):
        with pytest.raises(ValueError, match="target_url"):
            _feedback(_graph(), target_url=invalid)
    with pytest.raises(ValueError, match="target_host and target_url"):
        _feedback(
            _graph(),
            target_host="other.test",
            target_url="https://example.test",
        )


def test_shared_scan_job_across_origins_cannot_prove_target_negative_yield():
    graph = _two_origin_graph()
    for scheme in ("http", "https"):
        _record_completed_scan(
            graph,
            observation_id=f"scan:{scheme}",
            job_id="shared-scan-job",
            source="nuclei",
            asset_id=f"asset:{scheme}",
        )

    result = _feedback(
        graph,
        target_url="https://example.test",
        allowed=("map_forms", "detect_technology"),
    )
    assert result.state == "no_completed_scans"
    assert result.completed_scan_count == 0
    assert result.scanner_source_count == 0
    assert result.ambiguous_scan_source_jobs == 1
    assert result.recommended_task_kinds == ()
    assert result.negative_result_proves_safe is False


def test_cross_origin_job_cannot_poison_independent_target_scan():
    graph = _two_origin_graph()
    for scheme in ("http", "https"):
        _record_completed_scan(
            graph,
            observation_id=f"scan:shared:{scheme}",
            job_id="shared-scan-job",
            source="nuclei",
            asset_id=f"asset:{scheme}",
        )
    _record_completed_scan(
        graph,
        observation_id="scan:trusted:https",
        job_id="independent-https-job",
        source="nuclei",
        asset_id="asset:https",
    )

    result = _feedback(graph, target_url="https://example.test")
    assert result.state == "recovery_advisory"
    assert result.completed_scan_count == 1
    assert result.scanner_source_count == 1
    assert result.ambiguous_scan_source_jobs == 1
    assert result.recommended_task_kinds


def test_same_origin_reports_of_one_job_remain_one_trusted_scan():
    graph = _two_origin_graph()
    for index in range(2):
        _record_completed_scan(
            graph,
            observation_id=f"scan:duplicate:{index}",
            job_id="single-https-job",
            source="nuclei",
            asset_id="asset:https",
        )
    result = _feedback(graph, target_url="https://example.test")

    assert result.completed_scan_count == 1
    assert result.scanner_source_count == 1
    assert result.ambiguous_scan_source_jobs == 0


def test_scans_exclusively_on_another_origin_are_not_target_ambiguities():
    graph = _two_origin_graph()
    _record_completed_scan(
        graph,
        observation_id="scan:http-only",
        job_id="http-only-job",
        source="nuclei",
        asset_id="asset:http",
    )
    result = _feedback(graph, target_url="https://example.test")

    assert result.state == "no_completed_scans"
    assert result.completed_scan_count == 0
    assert result.ambiguous_scan_source_jobs == 0


def test_ambiguous_scan_jobs_do_not_trigger_premature_surface_rotation():
    graph = _graph(scans=0)
    for job in ("ambiguous-a", "ambiguous-b"):
        for source in ("nuclei", "strix"):
            _record_completed_scan(
                graph,
                observation_id=f"scan:{job}:{source}",
                job_id=job,
                source=source,
            )
    _record_completed_scan(
        graph,
        observation_id="scan:independent",
        job_id="independent",
        source="nuclei",
    )

    result = _feedback(graph, target_host="example.test")
    assert result.completed_scan_count == 3
    assert result.trusted_completed_scan_count == 1
    assert result.ambiguous_scan_source_jobs == 2
    assert result.state == "recovery_advisory"
    assert not any(
        "repeated completed scans yielded" in reason
        for reason in result.reasons
    )
    assert result.to_dict()["trusted_completed_scan_count"] == 1


def test_three_trusted_scans_can_trigger_coverage_rotation():
    result = _feedback(_graph(scans=3), target_host="example.test")

    assert result.completed_scan_count == 3
    assert result.trusted_completed_scan_count == 3
    assert result.ambiguous_scan_source_jobs == 0
    assert any(
        "repeated completed scans yielded" in reason
        for reason in result.reasons
    )


def test_only_ambiguous_scan_jobs_require_manual_source_review():
    graph = _graph(scans=0)
    _record_completed_scan(
        graph,
        observation_id="scan:missing-source",
        job_id="unknown-source",
        source=" ",
    )
    result = _feedback(graph, target_host="example.test")

    assert result.completed_scan_count == 1
    assert result.trusted_completed_scan_count == 0
    assert result.scanner_source_count == 0
    assert result.state == "scan_source_unverified"
    assert result.recommended_task_kinds == ()
    assert result.negative_result_proves_safe is False


def test_cross_origin_ambiguity_does_not_reduce_separate_trusted_job_count():
    graph = _two_origin_graph()
    for scheme in ("http", "https"):
        _record_completed_scan(
            graph,
            observation_id=f"scan:shared:{scheme}",
            job_id="one-job-two-origins",
            source="nuclei",
            asset_id=f"asset:{scheme}",
        )
    _record_completed_scan(
        graph,
        observation_id="scan:good:https",
        job_id="origin-specific-job",
        source="nuclei",
        asset_id="asset:https",
    )

    result = _feedback(graph, target_url="https://example.test")
    assert result.completed_scan_count == 1
    assert result.trusted_completed_scan_count == 1
    assert result.ambiguous_scan_source_jobs == 1
    assert result.state == "recovery_advisory"



def _scan_report(
    graph: ObservationGraph,
    *,
    report_id: str,
    findings: object,
    asset_id: str = "asset:a",
) -> None:
    graph.add(
        Observation(
            report_id,
            "evidence",
            "completed-scan",
            "nuclei",
            parent_ids=(asset_id,),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": report_id,
                "findings": findings,
            },
        )
    )


def test_positive_scan_count_with_no_recorded_finding_blocks_negative_recovery():
    graph = _graph(scans=0)
    _scan_report(graph, report_id="scan:positive", findings=2)
    result = _feedback(graph, target_url="https://example.test")

    assert result.state == "scan_findings_unreconciled"
    assert result.unreconciled_scan_reports == 1
    assert result.trusted_completed_scan_count == 1
    assert result.recommended_task_kinds == ()
    assert result.negative_result_proves_safe is False
    assert result.may_enable_exploitation is False


def test_explicit_zero_finding_count_retains_safe_recovery_guidance():
    graph = _graph(scans=0)
    _scan_report(graph, report_id="scan:zero", findings=0)
    result = _feedback(graph, target_url="https://example.test")

    assert result.state == "recovery_advisory"
    assert result.unreconciled_scan_reports == 0
    assert "map_forms" in result.recommended_task_kinds


def test_malformed_finding_counter_requires_ingestion_reconciliation():
    for value in (-1, True, "0", None, 1.5):
        graph = _graph(scans=0)
        _scan_report(graph, report_id="scan:malformed", findings=value)
        result = _feedback(graph, target_url="https://example.test")

        assert result.state == "scan_findings_unreconciled"
        assert result.unreconciled_scan_reports == 1
        assert result.recommended_task_kinds == ()


def test_other_origin_scan_finding_count_does_not_block_target_recovery():
    graph = _graph(scans=0)
    graph.add(Observation("asset:other", "asset", "other.test", "inventory"))
    _scan_report(
        graph,
        report_id="scan:other-positive",
        findings=3,
        asset_id="asset:other",
    )
    _scan_report(graph, report_id="scan:target-zero", findings=0)

    result = _feedback(
        graph,
        target_url="https://example.test",
        scope=lambda host: host in {"example.test", "other.test"},
    )

    assert result.state == "recovery_advisory"
    assert result.unreconciled_scan_reports == 0
    assert result.trusted_completed_scan_count == 1


def test_existing_findings_do_not_get_misclassified_as_missing_ingestion():
    graph = _graph(scans=0)
    _scan_report(graph, report_id="scan:positive", findings=1)
    graph.add(
        Observation(
            "finding:present",
            "finding",
            "candidate",
            "nuclei",
            parent_ids=("asset:a",),
        )
    )
    result = _feedback(graph, target_url="https://example.test")

    assert result.state == "findings_present"
    assert result.unreconciled_scan_reports == 0

def test_review_with_mixed_authorized_and_other_host_parents_is_not_coverage():
    graph = _graph(scans=0)
    graph.add(
        Observation(
            "scan:target",
            "evidence",
            "scan-complete",
            "nuclei",
            parent_ids=("asset:a",),
            metadata={
                "phase": "scan",
                "status": "completed",
                "job_id": "job-target",
                "findings": 0,
            },
        )
    )
    graph.add(Observation("asset:other", "asset", "other.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:other",
            "endpoint",
            "https://other.test/account",
            "crawler",
            parent_ids=("asset:other",),
        )
    )
    graph.add(
        Observation(
            "review:mixed",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:a", "endpoint:other"),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )

    result = _feedback(
        graph,
        target_url="https://example.test",
        scope=lambda host: host in {"example.test", "other.test"},
    )
    assert result.uncovered_endpoint_count == 1
    assert "map_endpoints" in result.recommended_task_kinds


def test_form_review_cannot_use_mixed_endpoint_parent_to_close_gap():
    graph = _graph()
    graph.add(
        Observation(
            "form:a",
            "form",
            "https://example.test/login",
            "browser",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "review:mixed-form",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("form:a", "endpoint:a"),
            metadata={
                "review_type": "form_surface_review",
                "status": "completed",
            },
        )
    )

    result = _feedback(graph)
    assert result.uncovered_form_count == 1
    assert "browser_observe" in result.recommended_task_kinds


def test_review_of_two_valid_target_endpoints_closes_both_gaps():
    graph = _graph()
    graph.add(
        Observation(
            "endpoint:b",
            "endpoint",
            "https://example.test/profile",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "review:both",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:a", "endpoint:b"),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )

    result = _feedback(graph)
    assert result.in_scope_endpoint_count == 2
    assert result.uncovered_endpoint_count == 0


def test_review_with_no_surface_parent_never_closes_coverage():
    graph = _graph()
    graph.add(
        Observation(
            "review:orphan",
            "evidence",
            "reviewed",
            "analyst",
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )

    assert _feedback(graph).uncovered_endpoint_count == 1
