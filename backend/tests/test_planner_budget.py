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
    assert usage.remaining_validations == 24


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
