from __future__ import annotations

from app.recon_priority import prioritize_recon_tasks
from app.recon_swarm import ReconTask


def task(kind: str, priority: int = 60) -> ReconTask:
    agents = {
        "crawl": "crawler-agent",
        "map_endpoints": "endpoint-agent",
        "detect_technology": "tech-agent",
        "map_forms": "form-agent",
        "browser_observe": "browser-agent",
    }
    return ReconTask(
        kind=kind,
        agent=agents[kind],
        target="https://app.example.com/",
        priority=priority,
        reason="fixture",
        max_requests=7,
    )


def test_diff_priority_only_reorders_existing_authorized_tasks():
    original = [
        task("detect_technology", 75),
        task("map_endpoints", 80),
        task("map_forms", 70),
    ]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 4,
            "counts_by_kind": {
                "asset": {"added": 0, "removed": 0},
                "endpoint": {"added": 2, "removed": 0},
                "form": {"added": 1, "removed": 0},
                "technology": {"added": 0, "removed": 0},
                "waf": {"added": 0, "removed": 0},
            },
        },
    }

    result = prioritize_recon_tasks(original, diff)

    assert len(result.tasks) == len(original)
    assert result.to_dict()["new_tasks_created"] is False
    assert result.to_dict()["scope_expansion"] is False
    assert result.to_dict()["target_rewrite"] is False
    assert result.to_dict()["execution_influence"] == "ordering_only"

    by_kind = {item.kind: item for item in result.tasks}
    before = {item.kind: item for item in original}
    assert by_kind["map_endpoints"].priority > before["map_endpoints"].priority
    assert by_kind["map_forms"].priority > before["map_forms"].priority
    assert by_kind["detect_technology"].priority == before["detect_technology"].priority

    for kind, updated in by_kind.items():
        source = before[kind]
        assert updated.target == source.target
        assert updated.agent == source.agent
        assert updated.max_requests == source.max_requests
        assert updated.allowed_methods == source.allowed_methods
        assert updated.same_origin_only == source.same_origin_only
        assert updated.read_only == source.read_only


def test_diff_priority_does_nothing_without_baseline():
    original = [task("map_endpoints", 80), task("map_forms", 70)]
    diff = {
        "baseline_available": False,
        "summary": {
            "change_count": 3,
            "counts_by_kind": {
                "endpoint": {"added": 3, "removed": 0},
                "form": {"added": 2, "removed": 0},
            },
        },
    }

    result = prioritize_recon_tasks(original, diff)

    assert [(item.kind, item.priority) for item in result.tasks] == [
        ("map_endpoints", 80),
        ("map_forms", 70),
    ]
    assert all(item.boost == 0 for item in result.adjustments)


def test_diff_priority_is_bounded_to_fifteen_points():
    original = [task("map_endpoints", 70)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 100,
            "counts_by_kind": {
                "endpoint": {"added": 100, "removed": 100},
                "asset": {"added": 100, "removed": 100},
            },
        },
    }

    result = prioritize_recon_tasks(original, diff)

    assert result.tasks[0].priority == 85
    assert result.adjustments[0].boost == 15
