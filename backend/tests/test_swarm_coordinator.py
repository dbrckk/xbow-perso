import pytest

from app.observation_graph import Observation, ObservationGraph
from app.recon_swarm import ReconTask, build_recon_plan
from app.swarm_coordinator import SwarmBudget, coordinate_recon_swarm


def _tasks():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    return build_recon_plan(
        "https://example.test",
        graph,
        scope_checker=lambda host: host == "example.test",
    )


def test_swarm_coordinator_preserves_capability_boundaries():
    result = coordinate_recon_swarm(_tasks())

    assert result.tasks
    assert result.request_budget_used <= 80
    assert result.request_budget_remaining >= 0
    assert set(result.active_agents) <= {
        "crawler-agent",
        "endpoint-agent",
        "tech-agent",
        "form-agent",
        "browser-agent",
    }
    assert all(task.read_only and task.same_origin_only for task in result.tasks)
    assert all(set(task.allowed_methods) <= {"GET", "HEAD"} for task in result.tasks)


def test_swarm_coordinator_shares_request_budget_across_agents():
    tasks = _tasks()
    result = coordinate_recon_swarm(
        tasks,
        SwarmBudget(max_tasks=5, max_total_requests=30, max_network_agents=5),
    )

    assert result.request_budget_used == 30
    assert result.request_budget_remaining == 0
    assert sum(task.max_requests for task in result.tasks) == 30
    assert result.suppressed_tasks


def test_swarm_coordinator_limits_agent_fanout():
    result = coordinate_recon_swarm(
        _tasks(),
        SwarmBudget(max_tasks=5, max_total_requests=80, max_network_agents=2),
    )

    assert len(result.active_agents) <= 2
    assert result.suppressed_tasks


def test_swarm_coordinator_fails_closed_on_agent_mismatch():
    bad = ReconTask(
        "crawl",
        "wrong-agent",
        "https://example.test/",
        100,
        "fixture",
        10,
    )

    with pytest.raises(ValueError, match="agent mismatch"):
        coordinate_recon_swarm([bad])


def test_swarm_coordinator_rejects_capability_escalation():
    bad = ReconTask(
        "crawl",
        "crawler-agent",
        "https://example.test/",
        100,
        "fixture",
        10,
        allowed_methods=("GET", "POST"),
    )

    with pytest.raises(ValueError, match="methods exceed agent capability"):
        coordinate_recon_swarm([bad])


def test_swarm_budget_validation_is_fail_closed():
    with pytest.raises(ValueError, match="max_total_requests"):
        SwarmBudget(max_total_requests=0)
