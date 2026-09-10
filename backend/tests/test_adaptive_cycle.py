from app.adaptive_cycle import build_adaptive_cycle
from app.autonomy_gate import AutonomyGate
from app.learning_memory import TechniqueMemory
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
