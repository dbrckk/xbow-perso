from app.observation_graph import PlannedAction
from app.planner_intelligence import prioritize_action_with_intelligence


def _intel(score: int = 80) -> dict:
    return {
        "focuses": [
            {
                "family": "graphql-authorization",
                "score": score,
                "matched_case_ids": ["public-case-1"],
                "observation_goals": ["compare authorized test roles"],
            }
        ]
    }


def test_priority_preserves_kind_and_target():
    original = PlannedAction("scan", "example.test", "safe planner transition", 80)
    action, context = prioritize_action_with_intelligence(original, _intel())
    assert action.kind == original.kind
    assert action.target == original.target
    assert action.priority >= original.priority
    assert action.priority < 100
    assert context["applied"] is True
    assert context["automatic_exploitation"] is False
    assert context["scope_expansion"] is False


def test_stop_is_never_reprioritized():
    original = PlannedAction("stop", "example.test", "policy blocked", 100)
    action, context = prioritize_action_with_intelligence(original, _intel(95))
    assert action == original
    assert context["applied"] is False


def test_weak_public_signal_does_not_change_action():
    original = PlannedAction("crawl", "example.test", "needs inventory", 90)
    action, context = prioritize_action_with_intelligence(original, _intel(35))
    assert action == original
    assert context["families"] == []
