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


def test_historical_novelty_adds_small_bounded_boost():
    original = [task("map_endpoints", 70)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 2,
            "counts_by_kind": {
                "endpoint": {"added": 1, "removed": 0},
                "asset": {"added": 0, "removed": 0},
            },
        },
    }
    memory = {
        "delta": {
            "added": [{"kind": "endpoint", "value": "https://app.example.com/new"}],
        },
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/new",
                "campaign_count": 1,
            }
        ],
    }

    result = prioritize_recon_tasks(original, diff, memory)

    adjustment = result.adjustments[0]
    assert adjustment.diff_boost == 4
    assert adjustment.history_boost == 1
    assert adjustment.boost == 5
    assert result.tasks[0].priority == 75
    assert adjustment.historical_signals == ("endpoint",)


def test_reappearing_surface_has_less_history_weight_than_novel_surface():
    original = [task("map_endpoints", 70)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 2,
            "counts_by_kind": {
                "endpoint": {"added": 1, "removed": 0},
                "asset": {"added": 0, "removed": 0},
            },
        },
    }
    novel = {
        "delta": {
            "added": [{"kind": "endpoint", "value": "https://app.example.com/new"}],
        },
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/new",
                "campaign_count": 1,
            }
        ],
    }
    recurring = {
        "delta": {
            "added": [{"kind": "endpoint", "value": "https://app.example.com/new"}],
        },
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/new",
                "campaign_count": 8,
            }
        ],
    }

    novel_result = prioritize_recon_tasks(original, diff, novel)
    recurring_result = prioritize_recon_tasks(original, diff, recurring)

    assert novel_result.adjustments[0].history_boost >= recurring_result.adjustments[0].history_boost


def test_total_priority_boost_is_bounded_to_twenty_points():
    original = [task("browser_observe", 60)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 100,
            "counts_by_kind": {
                "endpoint": {"added": 100, "removed": 0},
                "form": {"added": 100, "removed": 0},
                "technology": {"added": 100, "removed": 0},
            },
        },
    }
    memory = {
        "delta": {
            "added": [
                {"kind": "endpoint", "value": f"https://app.example.com/{i}"}
                for i in range(20)
            ]
            + [{"kind": "form", "value": f"POST /f{i}"} for i in range(20)],
        },
        "nodes": [
            {
                "kind": "endpoint",
                "value": f"https://app.example.com/{i}",
                "campaign_count": 1,
            }
            for i in range(20)
        ]
        + [
            {
                "kind": "form",
                "value": f"POST /f{i}",
                "campaign_count": 1,
            }
            for i in range(20)
        ],
    }

    result = prioritize_recon_tasks(original, diff, memory)

    assert result.adjustments[0].boost == 20
    assert result.tasks[0].priority == 80


def test_temporal_novelty_favors_never_seen_surface_over_returning_churn():
    original = [task("map_endpoints", 70)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 1,
            "counts_by_kind": {
                "endpoint": {"added": 1, "removed": 0},
                "asset": {"added": 0, "removed": 0},
            },
        },
    }
    memory = {
        "delta": {
            "added": [{"kind": "endpoint", "value": "https://app.example.com/feature"}],
        },
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/feature",
                "campaign_count": 1,
            }
        ],
    }
    new_temporal = {
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/feature",
                "classification": "new",
                "presence_ratio": 0.25,
            }
        ]
    }
    returning_temporal = {
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/feature",
                "classification": "returning",
                "presence_ratio": 0.75,
            }
        ]
    }

    new_result = prioritize_recon_tasks(original, diff, memory, new_temporal)
    returning_result = prioritize_recon_tasks(original, diff, memory, returning_temporal)

    assert new_result.adjustments[0].temporal_boost > returning_result.adjustments[0].temporal_boost
    assert new_result.tasks[0].priority >= returning_result.tasks[0].priority


def test_intermittent_surface_has_low_temporal_weight():
    original = [task("browser_observe", 60)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 1,
            "counts_by_kind": {
                "endpoint": {"added": 1, "removed": 0},
                "form": {"added": 0, "removed": 0},
                "technology": {"added": 0, "removed": 0},
            },
        },
    }
    temporal = {
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/beta",
                "classification": "intermittent",
                "presence_ratio": 0.6,
            }
        ]
    }

    result = prioritize_recon_tasks(original, diff, None, temporal)

    assert result.adjustments[0].temporal_boost <= 1


def test_temporal_scoring_never_breaks_total_boost_cap():
    original = [task("browser_observe", 60)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 100,
            "counts_by_kind": {
                "endpoint": {"added": 100, "removed": 0},
                "form": {"added": 100, "removed": 0},
                "technology": {"added": 100, "removed": 0},
            },
        },
    }
    memory = {
        "delta": {
            "added": [
                {"kind": "endpoint", "value": f"https://app.example.com/{i}"}
                for i in range(20)
            ],
        },
        "nodes": [
            {
                "kind": "endpoint",
                "value": f"https://app.example.com/{i}",
                "campaign_count": 1,
            }
            for i in range(20)
        ],
    }
    temporal = {
        "nodes": [
            {
                "kind": "endpoint",
                "value": f"https://app.example.com/{i}",
                "classification": "new",
                "presence_ratio": 0.1,
            }
            for i in range(20)
        ]
    }

    result = prioritize_recon_tasks(original, diff, memory, temporal)

    assert result.adjustments[0].boost == 20
    assert result.tasks[0].priority == 80


def test_low_confidence_dampens_recon_boost_without_changing_authority():
    original = [task("map_endpoints", 70)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 4,
            "counts_by_kind": {
                "endpoint": {"added": 3, "removed": 0},
                "asset": {"added": 1, "removed": 0},
            },
        },
    }
    confidence = {
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/new",
                "confidence": 0.2,
            },
            {
                "kind": "asset",
                "value": "app.example.com",
                "confidence": 0.3,
            },
        ]
    }

    result = prioritize_recon_tasks(original, diff, None, None, confidence)

    adjustment = result.adjustments[0]
    assert 0.5 <= adjustment.confidence_factor < 1.0
    assert adjustment.boost < adjustment.diff_boost
    assert result.tasks[0].target == original[0].target
    assert result.tasks[0].max_requests == original[0].max_requests
    assert result.tasks[0].allowed_methods == original[0].allowed_methods


def test_high_confidence_preserves_full_bounded_boost():
    original = [task("map_endpoints", 70)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 4,
            "counts_by_kind": {
                "endpoint": {"added": 3, "removed": 0},
                "asset": {"added": 1, "removed": 0},
            },
        },
    }
    confidence = {
        "nodes": [
            {
                "kind": "endpoint",
                "value": "https://app.example.com/new",
                "confidence": 1.0,
            },
            {
                "kind": "asset",
                "value": "app.example.com",
                "confidence": 1.0,
            },
        ]
    }

    result = prioritize_recon_tasks(original, diff, None, None, confidence)

    adjustment = result.adjustments[0]
    assert adjustment.confidence_factor == 1.0
    assert adjustment.boost == adjustment.diff_boost


def test_missing_confidence_is_neutral_and_never_increases_cap():
    original = [task("browser_observe", 60)]
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 100,
            "counts_by_kind": {
                "endpoint": {"added": 100, "removed": 0},
                "form": {"added": 100, "removed": 0},
                "technology": {"added": 100, "removed": 0},
            },
        },
    }

    result = prioritize_recon_tasks(original, diff, None, None, None)

    assert result.adjustments[0].confidence_factor == 1.0
    assert result.adjustments[0].boost <= 20



def test_high_value_focus_boosts_matching_existing_task_only():
    original = [
        task("map_endpoints", 60),
        task("detect_technology", 60),
    ]
    diff = {
        "baseline_available": False,
        "summary": {"change_count": 0, "counts_by_kind": {}},
    }
    high_value = {
        "focuses": [
            {
                "family": "graphql-authorization",
                "score": 80,
            }
        ]
    }

    result = prioritize_recon_tasks(
        original,
        diff,
        None,
        None,
        None,
        high_value,
    )

    by_kind = {item.kind: item for item in result.tasks}
    adjustments = {item.kind: item for item in result.adjustments}

    assert by_kind["map_endpoints"].priority > 60
    assert adjustments["map_endpoints"].high_value_boost > 0
    assert "graphql-authorization" in adjustments["map_endpoints"].high_value_families
    assert by_kind["detect_technology"].priority == 60
    assert adjustments["detect_technology"].high_value_boost == 0


def test_high_value_boost_preserves_recon_authority_fields():
    source = task("browser_observe", 65)
    diff = {
        "baseline_available": False,
        "summary": {"change_count": 0, "counts_by_kind": {}},
    }
    high_value = {
        "focuses": [
            {"family": "authentication-state-machine", "score": 90},
            {"family": "graphql-data-segregation", "score": 75},
        ]
    }

    result = prioritize_recon_tasks(
        [source],
        diff,
        None,
        None,
        None,
        high_value,
    )

    updated = result.tasks[0]
    assert updated.kind == source.kind
    assert updated.target == source.target
    assert updated.agent == source.agent
    assert updated.max_requests == source.max_requests
    assert updated.allowed_methods == source.allowed_methods
    assert updated.same_origin_only == source.same_origin_only
    assert updated.read_only == source.read_only
    assert result.adjustments[0].boost <= 25
