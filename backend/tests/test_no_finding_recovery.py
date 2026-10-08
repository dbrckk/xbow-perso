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
            metadata={"review_type": "form_surface_review"},
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
            metadata={"review_type": "authorization_surface_review"},
        )
    )
    graph.add(
        Observation(
            "review:form",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("form:one",),
            metadata={"review_type": "form_surface_review"},
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
