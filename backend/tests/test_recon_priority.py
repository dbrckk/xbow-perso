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



def test_fully_covered_high_value_family_does_not_receive_extra_boost():
    original = [task("map_endpoints", 60)]
    diff = {
        "baseline_available": False,
        "summary": {"change_count": 0, "counts_by_kind": {}},
    }
    high_value = {
        "focuses": [
            {
                "family": "graphql-authorization",
                "score": 90,
                "undercovered_high_value_score": 0,
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

    assert result.tasks[0].priority == 60
    assert result.adjustments[0].high_value_boost == 0


def test_undercovered_high_value_score_drives_existing_task_boost():
    original = [task("map_endpoints", 60)]
    diff = {
        "baseline_available": False,
        "summary": {"change_count": 0, "counts_by_kind": {}},
    }
    high_value = {
        "focuses": [
            {
                "family": "graphql-authorization",
                "score": 90,
                "undercovered_high_value_score": 72,
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

    assert result.tasks[0].priority > 60
    assert result.adjustments[0].high_value_boost > 0


def test_no_finding_recovery_reorders_existing_recon_without_expanding_authority():
    original = [
        task("map_endpoints", 80),
        task("map_forms", 70),
        task("detect_technology", 75),
    ]
    feedback = {
        "state": "recovery_advisory",
        "advisory_only": True,
        "may_expand_scope": False,
        "may_increase_request_budget": False,
        "recommended_task_kinds": ["map_forms", "detect_technology"],
    }
    result = prioritize_recon_tasks(
        original,
        {"baseline_available": False, "summary": {}},
        no_finding_feedback=feedback,
    )

    assert result.tasks[0].kind == "map_forms"
    assert result.adjustments[0].no_finding_boost == 24
    assert all(0 <= item.boost <= 25 for item in result.adjustments)
    assert [item.kind for item in result.tasks] == [
        "map_forms", "detect_technology", "map_endpoints"
    ]
    before = {item.kind: item for item in original}
    for item in result.tasks:
        source = before[item.kind]
        assert item.target == source.target
        assert item.max_requests == source.max_requests
        assert item.allowed_methods == source.allowed_methods
        assert item.same_origin_only == source.same_origin_only
        assert item.read_only == source.read_only
    assert result.to_dict()["new_tasks_created"] is False
    assert result.to_dict()["execution_influence"] == "ordering_only"


def test_no_finding_feedback_cannot_override_authority_fields():
    original = [task("map_forms", 70)]
    invalid_feedback = {
        "state": "recovery_advisory",
        "advisory_only": True,
        "may_expand_scope": True,
        "may_increase_request_budget": False,
        "recommended_task_kinds": ["map_forms"],
    }
    result = prioritize_recon_tasks(
        original,
        {"baseline_available": False, "summary": {}},
        no_finding_feedback=invalid_feedback,
    )
    assert result.tasks == tuple(original)
    assert result.adjustments[0].no_finding_boost == 0


def test_no_finding_feedback_ignored_when_findings_present():
    original = [task("map_forms", 70)]
    feedback = {
        "state": "findings_present",
        "advisory_only": True,
        "may_expand_scope": False,
        "may_increase_request_budget": False,
        "recommended_task_kinds": ["map_forms"],
    }
    result = prioritize_recon_tasks(
        original,
        {"baseline_available": False, "summary": {}},
        no_finding_feedback=feedback,
    )
    assert result.tasks == tuple(original)
    assert result.adjustments[0].no_finding_boost == 0


def test_feedback_never_creates_unconfigured_recon_tasks():
    result = prioritize_recon_tasks(
        [task("map_endpoints", 70)],
        {"baseline_available": False, "summary": {}},
        no_finding_feedback={
            "state": "recovery_advisory",
            "advisory_only": True,
            "may_expand_scope": False,
            "may_increase_request_budget": False,
            "recommended_task_kinds": ["arbitrary_shell", "map_forms"],
        },
    )
    assert len(result.tasks) == 1
    assert result.tasks[0].kind == "map_endpoints"
    assert result.adjustments[0].no_finding_boost == 0


def _safe_feedback(*, state="recovery_advisory", exhausted=(), reopened=(), recommended=()):
    return {
        "state": state,
        "advisory_only": True,
        "may_expand_scope": False,
        "may_increase_request_budget": False,
        "may_enable_exploitation": False,
        "may_change_execution_gate": False,
        "recommended_task_kinds": list(recommended),
        "exhausted_task_kinds": list(exhausted),
        "reopened_task_kinds": list(reopened),
    }


def test_negative_scan_exhaustion_deprioritizes_repeated_task_but_keeps_visibility():
    original = [
        task("map_endpoints", 80),
        task("map_forms", 70),
    ]
    result = prioritize_recon_tasks(
        original,
        {"baseline_available": False, "summary": {}},
        no_finding_feedback=_safe_feedback(
            exhausted=("map_endpoints",),
            recommended=("map_forms",),
        ),
    )
    by_kind = {item.kind: item for item in result.tasks}
    audit = {item.kind: item for item in result.adjustments}

    assert by_kind["map_forms"].priority > by_kind["map_endpoints"].priority
    assert audit["map_endpoints"].no_finding_penalty == 20
    assert audit["map_endpoints"].no_finding_boost == 0
    assert audit["map_endpoints"].boost == 0
    assert "manual review" in by_kind["map_endpoints"].reason
    assert len(result.tasks) == len(original)
    assert result.to_dict()["execution_influence"] == "ordering_only"
    assert result.to_dict()["new_tasks_created"] is False
    for item in result.tasks:
        baseline = next(source for source in original if source.kind == item.kind)
        assert item.target == baseline.target
        assert item.agent == baseline.agent
        assert item.max_requests == baseline.max_requests
        assert item.allowed_methods == baseline.allowed_methods
        assert item.read_only == baseline.read_only


def test_exhaustion_prevents_historical_priority_inflation():
    source = task("map_endpoints", 80)
    diff = {
        "baseline_available": True,
        "summary": {
            "change_count": 20,
            "counts_by_kind": {"endpoint": {"added": 10, "removed": 0}},
        },
    }
    result = prioritize_recon_tasks(
        [source],
        diff,
        no_finding_feedback=_safe_feedback(exhausted=("map_endpoints",)),
    )

    assert result.tasks[0].priority == 60
    assert result.adjustments[0].boost == 0
    assert result.adjustments[0].no_finding_penalty == 20


def test_reopened_recovery_kind_is_not_penalized():
    source = task("map_forms", 70)
    feedback = _safe_feedback(
        exhausted=("map_forms",),
        reopened=("map_forms",),
        recommended=("map_forms",),
    )
    result = prioritize_recon_tasks(
        [source],
        {"baseline_available": False, "summary": {}},
        no_finding_feedback=feedback,
    )

    assert result.tasks[0].priority > source.priority
    assert result.adjustments[0].no_finding_penalty == 0
    assert result.adjustments[0].no_finding_boost == 24


def test_no_supported_recovery_tasks_are_penalized_not_dispatched():
    sources = [task("map_forms", 70), task("detect_technology", 75)]
    result = prioritize_recon_tasks(
        sources,
        {"baseline_available": False, "summary": {}},
        no_finding_feedback=_safe_feedback(
            state="no_supported_recovery_task",
            exhausted=("map_forms", "detect_technology"),
        ),
    )

    assert len(result.tasks) == len(sources)
    assert all(item.no_finding_penalty == 20 for item in result.adjustments)
    assert all(item.no_finding_boost == 0 for item in result.adjustments)
    assert result.to_dict()["new_tasks_created"] is False


def test_malformed_or_escalating_feedback_does_not_deprioritize():
    source = task("map_forms", 70)
    feedback = _safe_feedback(exhausted=("map_forms",))
    feedback["may_enable_exploitation"] = True
    result = prioritize_recon_tasks(
        [source],
        {"baseline_available": False, "summary": {}},
        no_finding_feedback=feedback,
    )
    assert result.tasks == (source,)

    feedback = _safe_feedback(exhausted=("map_forms",))
    feedback["reopened_task_kinds"] = [["malformed"], "map_forms"]
    result = prioritize_recon_tasks(
        [source],
        {"baseline_available": False, "summary": {}},
        no_finding_feedback=feedback,
    )
    assert result.adjustments[0].no_finding_penalty == 0
