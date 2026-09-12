import pytest

from app.pipeline_swarm import coordinate_pipeline_action
from app.planner_budget import BudgetUsage, PlannerBudget


def _usage(**overrides):
    values = {
        "actions": 1,
        "scans": 0,
        "validations": 0,
        "reports": 0,
        "inflight_jobs": 0,
        "failed_jobs": 0,
        "remaining_actions": 49,
        "remaining_scans": 3,
        "remaining_validations": 25,
        "remaining_reports": 5,
        "remaining_inflight_jobs": 12,
        "remaining_failed_jobs": 5,
        "blocked_actions": {},
        "exhausted": False,
        "reason": None,
    }
    values.update(overrides)
    return BudgetUsage(**values)


def test_pipeline_swarm_uses_registered_specialized_agents():
    scan = coordinate_pipeline_action("scan", 2, _usage())
    validate = coordinate_pipeline_action("validate", 4, _usage())
    report = coordinate_pipeline_action("report", 1, _usage())

    assert (scan.agent, scan.role) == ("analysis-agent", "analysis")
    assert (validate.agent, validate.role) == ("validation-agent", "validation")
    assert (report.agent, report.role) == ("report-agent", "reporting")


def test_pipeline_swarm_shares_inflight_capacity_across_stages():
    usage = _usage(remaining_inflight_jobs=1)

    scan = coordinate_pipeline_action("scan", 2, usage)
    validate = coordinate_pipeline_action("validate", 10, usage)
    report = coordinate_pipeline_action("report", 1, usage)

    assert scan.allocated_items == 1
    assert validate.allocated_items == 1
    assert report.allocated_items == 1
    assert scan.remaining_inflight_jobs == 0


def test_pipeline_swarm_respects_stage_specific_budgets():
    limits = PlannerBudget(
        max_scans=3,
        max_validations=25,
        max_validation_batch=4,
        max_reports=5,
        max_inflight_jobs=12,
    )
    usage = _usage(
        remaining_scans=1,
        remaining_validations=20,
        remaining_reports=0,
    )

    assert coordinate_pipeline_action("scan", 2, usage, limits).allocated_items == 1
    assert coordinate_pipeline_action("validate", 10, usage, limits).allocated_items == 4
    assert coordinate_pipeline_action("report", 1, usage, limits).allocated_items == 0


def test_pipeline_swarm_rejects_unknown_action_and_negative_request():
    with pytest.raises(ValueError, match="unsupported pipeline action"):
        coordinate_pipeline_action("crawl", 1, _usage())

    with pytest.raises(ValueError, match="non-negative"):
        coordinate_pipeline_action("scan", -1, _usage())
