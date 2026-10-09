from app.adaptive_cycle import build_adaptive_cycle
from app.autonomy_gate import AutonomyGate
from app.learning_memory import TechniqueMemory
from app.main import app
from app.observation_graph import PlannedAction


def _gate(*, blocked: bool = False, human: bool = False, focus: str = "review_surface") -> AutonomyGate:
    return AutonomyGate(
        safe_autonomy_ready=not blocked and not human,
        human_review_required=human,
        next_focus=focus,
        blockers=("blocked",) if blocked else (),
        safeguards=("fail_closed_on_conflict",),
    )


def test_cycle_halts_when_gate_is_blocked():
    cycle = build_adaptive_cycle(
        _gate(blocked=True),
        [PlannedAction("crawl", "example.test", "crawl", 90)],
        [],
    )
    assert cycle.state == "halt"
    assert cycle.next_action == "stop"
    assert cycle.safe_to_progress is False


def test_cycle_maps_safe_planner_actions_to_bounded_states():
    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("crawl", "example.test", "crawl", 90)],
        [],
    )
    assert cycle.state == "recon"
    assert cycle.next_action == "crawl"
    assert cycle.safe_to_progress is True


def test_cycle_requires_human_for_report_focus():
    cycle = build_adaptive_cycle(
        _gate(human=True, focus="review_for_report"),
        [PlannedAction("report", "example.test", "report", 70)],
        [],
    )
    assert cycle.state == "human_review"
    assert cycle.requires_human is True
    assert cycle.safe_to_progress is False


def test_cycle_suppresses_repeated_failed_techniques():
    memory = TechniqueMemory(
        technique="bounded-review",
        attempts=2,
        successes=0,
        failures=2,
        inconclusive=0,
        success_rate=0.0,
        confidence=0.4,
        source_count=2,
    )
    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("scan", "example.test", "review", 80)],
        [memory],
    )
    assert cycle.retry_suppressed_techniques == ("bounded-review",)
    assert cycle.state == "review"


def test_adaptive_cycle_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/adaptive-cycle" in app.openapi()["paths"]


def test_cycle_halts_for_human_review_after_repeated_requeues_without_success():
    worker_outcomes = {
        "by_job_kind": {
            "recon_task": {
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
                "requeued": 2,
            }
        }
    }

    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("crawl", "example.test", "crawl", 90)],
        [],
        worker_outcomes,
    )

    assert cycle.state == "human_review"
    assert cycle.next_action == "stop"
    assert cycle.safe_to_progress is False
    assert cycle.requires_human is True
    assert cycle.retry_suppressed_job_kinds == ("recon_task",)


def test_cycle_does_not_suppress_recovered_worker_kind():
    worker_outcomes = {
        "by_job_kind": {
            "recon_task": {
                "completed": 1,
                "failed": 0,
                "cancelled": 0,
                "requeued": 2,
            }
        }
    }

    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("crawl", "example.test", "crawl", 90)],
        [],
        worker_outcomes,
    )

    assert cycle.state == "recon"
    assert cycle.safe_to_progress is True
    assert cycle.retry_suppressed_job_kinds == ()


def test_negative_scanner_memory_does_not_suppress_authorized_scanner():
    memory = TechniqueMemory(
        technique="scanner:nuclei",
        attempts=10,
        successes=0,
        failures=10,
        inconclusive=0,
        success_rate=0.0,
        confidence=1.0,
        source_count=2,
    )
    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("scan", "example.test", "review", 80)],
        [memory],
    )

    assert cycle.retry_suppressed_techniques == ()
    assert cycle.next_action == "scan"
    assert cycle.state == "review"
    assert cycle.safe_to_progress is True


def test_operational_scanner_worker_instability_still_requires_human_review():
    memory = TechniqueMemory(
        technique="scanner:nuclei",
        attempts=3,
        successes=0,
        failures=3,
        inconclusive=0,
        success_rate=0.0,
        confidence=1.0,
        source_count=2,
    )
    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("scan", "example.test", "review", 80)],
        [memory],
        {
            "by_job_kind": {
                "nuclei_scan": {
                    "completed": 0,
                    "requeued": 3,
                }
            }
        },
    )

    assert cycle.retry_suppressed_techniques == ()
    assert cycle.retry_suppressed_job_kinds == ("nuclei_scan",)
    assert cycle.state == "human_review"
    assert cycle.safe_to_progress is False
    assert cycle.requires_human is True


def test_malformed_worker_requeue_count_requires_review_not_exception():
    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("crawl", "example.test", "crawl", 90)],
        [],
        {"by_job_kind": {"recon_task": {"completed": 0, "requeued": "invalid"}}},
    )

    assert cycle.state == "human_review"
    assert cycle.next_action == "stop"
    assert cycle.requires_human is True
    assert cycle.retry_suppressed_job_kinds == ("recon_task",)


def test_negative_and_boolean_worker_counts_do_not_signal_healthy_execution():
    for bad in (-1, True, None, float("nan")):
        cycle = build_adaptive_cycle(
            _gate(),
            [PlannedAction("crawl", "example.test", "crawl", 90)],
            [],
            {"by_job_kind": {"recon_task": {"completed": bad, "requeued": 0}}},
        )
        assert cycle.state == "human_review"
        assert cycle.safe_to_progress is False
        assert cycle.retry_suppressed_job_kinds == ("recon_task",)


def test_malformed_worker_outcome_structure_requires_human_review():
    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("crawl", "example.test", "crawl", 90)],
        [],
        {"by_job_kind": []},
    )
    assert cycle.state == "human_review"
    assert cycle.retry_suppressed_job_kinds == ("untrusted_worker_outcomes",)


def test_valid_worker_feedback_retains_existing_completion_semantics():
    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("crawl", "example.test", "crawl", 90)],
        [],
        {"by_job_kind": {"recon_task": {"completed": 1, "requeued": 8}}},
    )
    assert cycle.state == "recon"
    assert cycle.safe_to_progress is True
    assert cycle.retry_suppressed_job_kinds == ()


def test_repeated_failed_workers_require_review_without_requeue_events():
    cycle = build_adaptive_cycle(
        _gate(),
        [PlannedAction("scan", "example.test", "scan", 80)],
        [],
        {"by_job_kind": {"nuclei_scan": {
            "completed": 0, "failed": 2, "requeued": 0
        }}},
    )
    assert cycle.state == "human_review"
    assert cycle.retry_suppressed_job_kinds == ("nuclei_scan",)
    assert cycle.safe_to_progress is False
