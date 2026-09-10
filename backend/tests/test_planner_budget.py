import pytest

from app.jobqueue import JobQueue
from app.observation_graph import Observation, ObservationGraph, PlannedAction
from app.planner_budget import PlannerBudget, apply_budget, budget_usage, validation_batch_limit


def test_budget_usage_reads_durable_campaign_jobs(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    queue.enqueue("c1", "independent_validation", {"finding_id": "f1"}, dedupe_key="validation:f1")
    queue.enqueue("c1", "report", {"platform": "generic"}, dedupe_key="report:1")
    queue.enqueue("other", "report", {"platform": "generic"}, dedupe_key="report:other")

    usage = budget_usage(graph, queue, "c1")

    assert usage.validations == 1
    assert usage.reports == 1
    assert usage.scans == 0
    assert usage.inflight_jobs == 2
    assert usage.failed_jobs == 0
    assert usage.remaining_validations == 24
    assert usage.blocked_actions == {}


def test_validate_action_stops_when_validation_budget_is_exhausted(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_validations=2, max_validation_batch=2)
    for finding_id in ("f1", "f2"):
        queue.enqueue(
            "c1",
            "independent_validation",
            {"finding_id": finding_id},
            dedupe_key=f"validation:{finding_id}",
        )

    action, usage = apply_budget(
        PlannedAction("validate", "example.test", "findings need validation", 90),
        graph,
        queue,
        "c1",
        limits,
    )

    assert action.kind == "stop"
    assert action.reason == "validation budget exhausted"
    assert usage.exhausted is True
    assert usage.remaining_validations == 0
    assert usage.blocked_actions["validate"] == "validation budget exhausted"


def test_scan_limit_does_not_block_unrelated_report_action(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_scans=1)
    queue.enqueue("c1", "strix_scan", {"target": "https://example.test"}, dedupe_key="scan:1")

    action, usage = apply_budget(
        PlannedAction("report", "example.test", "validation complete", 70),
        graph,
        queue,
        "c1",
        limits,
    )

    assert action.kind == "report"
    assert usage.remaining_scans == 0
    assert usage.exhausted is False
    assert usage.blocked_actions == {"scan": "scan budget exhausted"}


def test_total_action_budget_fails_closed(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    graph.add(
        Observation(
            "d1",
            "evidence",
            "scan",
            "orchestrator",
            metadata={
                "memory_type": "planner_decision",
                "action": "scan",
                "agent": "analysis-agent",
                "reason": "test",
                "priority": 80,
                "graph_fingerprint": "abc",
            },
        )
    )
    limits = PlannerBudget(max_actions=1)

    action, usage = apply_budget(
        PlannedAction("report", "example.test", "ready", 70),
        graph,
        queue,
        "c1",
        limits,
    )

    assert action.kind == "stop"
    assert action.reason == "planner action budget exhausted"
    assert usage.actions == 1
    assert usage.exhausted is True
    assert set(usage.blocked_actions) == {"inventory", "crawl", "scan", "validate", "report"}


def test_validation_batch_is_bounded_by_batch_and_remaining_budget(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_validations=12, max_validation_batch=10)
    for index in range(5):
        queue.enqueue(
            "c1",
            "independent_validation",
            {"finding_id": f"f{index}"},
            dedupe_key=f"validation:f{index}",
        )

    usage = budget_usage(graph, queue, "c1", limits)

    assert validation_batch_limit(usage, limits) == 7


def test_inflight_budget_stops_new_network_work(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_inflight_jobs=2)
    queue.enqueue("c1", "report", {"platform": "generic"}, dedupe_key="report:1")
    queue.enqueue("c1", "report", {"platform": "bugcrowd"}, dedupe_key="report:2")

    action, usage = apply_budget(
        PlannedAction("scan", "example.test", "scan next", 80),
        graph,
        queue,
        "c1",
        limits,
    )

    assert action.kind == "stop"
    assert action.reason == "in-flight job budget exhausted"
    assert usage.inflight_jobs == 2
    assert usage.remaining_inflight_jobs == 0
    assert usage.blocked_actions == {
        "scan": "in-flight job budget exhausted",
        "validate": "in-flight job budget exhausted",
        "report": "in-flight job budget exhausted",
    }


def test_validation_batch_respects_inflight_capacity(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_validations=20, max_validation_batch=10, max_inflight_jobs=6)
    for index in range(4):
        queue.enqueue(
            "c1",
            "report",
            {"campaign_id": "c1", "platform": f"generic-{index}"},
            dedupe_key=f"report:{index}",
        )

    usage = budget_usage(graph, queue, "c1", limits)

    assert usage.inflight_jobs == 4
    assert validation_batch_limit(usage, limits) == 2


def test_repeated_failed_jobs_stop_new_network_work(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_failed_jobs=2)

    for index in range(2):
        queued = queue.enqueue(
            "c1",
            "report",
            {"campaign_id": "c1", "platform": f"failed-{index}"},
            max_attempts=1,
            dedupe_key=f"failed:{index}",
        )
        claimed = queue.claim("worker-1")
        assert claimed is not None and claimed["id"] == queued["id"]
        queue.finish(claimed["id"], "worker-1", False, "expected test failure")

    action, usage = apply_budget(
        PlannedAction("validate", "example.test", "validate next", 80),
        graph,
        queue,
        "c1",
        limits,
    )

    assert action.kind == "stop"
    assert action.reason == "failed job budget exhausted"
    assert usage.failed_jobs == 2
    assert usage.remaining_failed_jobs == 0
    assert usage.blocked_actions == {
        "scan": "failed job budget exhausted",
        "validate": "failed job budget exhausted",
        "report": "failed job budget exhausted",
    }


def test_stop_action_is_never_blocked_by_job_budgets(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_inflight_jobs=1)
    queue.enqueue("c1", "report", {"platform": "generic"}, dedupe_key="report:1")

    requested = PlannedAction("stop", "example.test", "policy stop", 100)
    action, usage = apply_budget(requested, graph, queue, "c1", limits)

    assert action == requested
    assert usage.blocked_actions["report"] == "in-flight job budget exhausted"


def test_local_inventory_is_not_blocked_by_failed_job_budget(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_failed_jobs=1)
    queued = queue.enqueue(
        "c1",
        "report",
        {"campaign_id": "c1", "platform": "failed"},
        max_attempts=1,
        dedupe_key="failed:local-test",
    )
    claimed = queue.claim("worker-1")
    assert claimed is not None and claimed["id"] == queued["id"]
    queue.finish(claimed["id"], "worker-1", False, "expected test failure")

    requested = PlannedAction("inventory", "example.test", "seed target", 100)
    action, usage = apply_budget(requested, graph, queue, "c1", limits)

    assert action == requested
    assert usage.blocked_actions["scan"] == "failed job budget exhausted"


def test_validation_batch_is_zero_when_no_inflight_capacity_remains(tmp_path):
    queue = JobQueue(str(tmp_path / "db.sqlite3"))
    graph = ObservationGraph()
    limits = PlannerBudget(max_inflight_jobs=1)
    queue.enqueue("c1", "report", {"platform": "generic"}, dedupe_key="report:capacity")

    usage = budget_usage(graph, queue, "c1", limits)

    assert usage.remaining_inflight_jobs == 0
    assert validation_batch_limit(usage, limits) == 0


def test_budget_rejects_non_positive_limits():
    with pytest.raises(ValueError, match="positive"):
        PlannerBudget(max_failed_jobs=0)


def test_budget_rejects_validation_batch_larger_than_total_limit():
    with pytest.raises(ValueError, match="max_validation_batch"):
        PlannerBudget(max_validations=2, max_validation_batch=3)
