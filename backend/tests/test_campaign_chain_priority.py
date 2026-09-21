from app.campaign_chain_priority import build_campaign_chain_context, prioritize_with_chain_context
from app.observation_graph import Observation, ObservationGraph, PlannedAction


def test_chain_requires_multiple_observed_categories():
    graph = ObservationGraph()
    graph.add(Observation("e1", "endpoint", "https://example.test/graphql", "test"))
    context = build_campaign_chain_context(graph, {"focuses": []})
    assert context["candidates"] == []
    assert context["historical_award_used_as_target_evidence"] is False


def test_observed_auth_and_api_can_form_advisory_candidate():
    graph = ObservationGraph()
    graph.add(Observation("e1", "endpoint", "https://example.test/graphql", "test"))
    graph.add(Observation("e2", "endpoint", "https://example.test/oauth/login", "test"))
    context = build_campaign_chain_context(graph, {"focuses": []})
    assert context["candidates"]
    assert context["automatic_execution"] is False


def test_chain_priority_never_changes_kind_or_target():
    action = PlannedAction("validate", "example.test", "needs validation", 90)
    context = {
        "candidates": [{"chain_id": "auth-access-api", "completeness": 1.0}],
    }
    updated, meta = prioritize_with_chain_context(action, context)
    assert updated.kind == action.kind
    assert updated.target == action.target
    assert updated.priority < 100
    assert meta["scope_expansion"] is False
    assert meta["automatic_execution"] is False


def test_stop_is_immutable():
    action = PlannedAction("stop", "example.test", "policy blocked", 100)
    updated, meta = prioritize_with_chain_context(
        action,
        {"candidates": [{"chain_id": "x", "completeness": 1.0}]},
    )
    assert updated == action
    assert meta["applied"] is False
