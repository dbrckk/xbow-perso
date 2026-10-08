import pytest

from app.learning_memory import TechniqueMemory
from app.scanner_adaptation import adapt_scanner_engines


def _memory(engine, *, successes=0, failures=0, confidence=0.0, success_rate=0.0):
    return TechniqueMemory(
        technique=f"scanner:{engine}",
        attempts=successes + failures,
        successes=successes,
        failures=failures,
        inconclusive=0,
        success_rate=success_rate,
        confidence=confidence,
        source_count=2,
    )


def test_adaptation_never_expands_configured_engines():
    result = adapt_scanner_engines(
        ("strix",),
        [_memory("nuclei", successes=3, confidence=1.0, success_rate=1.0)],
        {},
    )

    assert result.configured_engines == ("strix",)
    assert result.selected_engines == ("strix",)
    assert "nuclei" not in result.selected_engines
    assert result.may_expand_configuration is False


def test_adaptation_preserves_engine_after_negative_technique_outcomes():
    result = adapt_scanner_engines(
        ("strix", "nuclei"),
        [_memory("nuclei", failures=2, confidence=0.8, success_rate=0.0)],
        {},
    )

    assert set(result.selected_engines) == {"strix", "nuclei"}
    assert result.suppressed_engines == ()
    assert "do not prove scanner failure" in result.reasons["nuclei"]


def test_adaptation_never_suppresses_last_configured_engine():
    result = adapt_scanner_engines(
        ("nuclei",),
        [_memory("nuclei", failures=3, confidence=1.0, success_rate=0.0)],
        {
            "by_job_kind": {
                "nuclei_scan": {
                    "completed": 0,
                    "failed": 2,
                    "cancelled": 0,
                    "requeued": 0,
                }
            }
        },
    )

    assert result.selected_engines == ("nuclei",)
    assert result.suppressed_engines == ()
    assert "at least one configured scanner must remain" in result.reasons["nuclei"]


def test_adaptation_ranks_successful_memory_first():
    result = adapt_scanner_engines(
        ("strix", "nuclei"),
        [
            _memory("strix", successes=1, confidence=0.4, success_rate=1.0),
            _memory("nuclei", successes=3, confidence=0.8, success_rate=1.0),
        ],
        {},
    )

    assert result.ranked_engines == ("nuclei", "strix")
    assert result.selected_engines == ("nuclei", "strix")


def test_adaptation_rejects_unknown_or_duplicate_configuration():
    with pytest.raises(ValueError, match="unsupported configured scanner engine"):
        adapt_scanner_engines(("strix", "shell"), [], {})

    with pytest.raises(ValueError, match="must be unique"):
        adapt_scanner_engines(("strix", "strix"), [], {})


def test_adaptation_suppresses_genuinely_unstable_worker_when_alternative_exists():
    result = adapt_scanner_engines(
        ("strix", "nuclei"),
        [_memory("nuclei", failures=4, confidence=1.0)],
        {
            "by_job_kind": {
                "nuclei_scan": {
                    "completed": 0,
                    "failed": 2,
                    "requeued": 1,
                }
            }
        },
    )

    assert result.selected_engines == ("strix",)
    assert result.suppressed_engines == ("nuclei",)
    assert "unstable execution" in result.reasons["nuclei"]


def test_completed_scanner_run_overrides_negative_memory_for_suppression():
    result = adapt_scanner_engines(
        ("strix", "nuclei"),
        [_memory("nuclei", failures=8, confidence=1.0)],
        {
            "by_job_kind": {
                "nuclei_scan": {
                    "completed": 1,
                    "failed": 2,
                    "requeued": 2,
                }
            }
        },
    )

    assert "nuclei" in result.selected_engines
    assert result.suppressed_engines == ()
    assert "do not prove scanner failure" in result.reasons["nuclei"]


def test_negative_memory_cannot_expand_scanner_configuration():
    result = adapt_scanner_engines(
        ("nuclei",),
        [_memory("nuclei", failures=6, confidence=1.0)],
        {},
    )

    assert result.selected_engines == ("nuclei",)
    assert result.configured_engines == ("nuclei",)
    assert result.may_expand_configuration is False
    assert result.advisory_only is True


def test_negative_only_memory_does_not_out_rank_configured_engine_order():
    result = adapt_scanner_engines(
        ("strix", "nuclei"),
        [_memory("nuclei", failures=10, confidence=1.0)],
        {},
    )

    assert result.selected_engines == ("strix", "nuclei")
    assert result.ranked_engines == ("strix", "nuclei")
    assert result.suppressed_engines == ()


def test_positive_scanner_evidence_can_improve_ranking_without_new_engines():
    result = adapt_scanner_engines(
        ("strix", "nuclei"),
        [
            _memory("strix", failures=9, confidence=1.0),
            _memory("nuclei", successes=2, confidence=0.4, success_rate=1.0),
        ],
        {},
    )

    assert result.ranked_engines == ("nuclei", "strix")
    assert result.configured_engines == ("strix", "nuclei")
    assert result.may_expand_configuration is False


def test_repeated_negative_runs_prioritize_unobserved_configured_engine():
    result = adapt_scanner_engines(
        ("nuclei", "strix"),
        [_memory("nuclei", failures=4, confidence=0.8)],
        {
            "by_job_kind": {
                "nuclei_scan": {"completed": 4, "failed": 0, "requeued": 0},
            }
        },
    )

    assert result.selected_engines == ("strix", "nuclei")
    assert result.ranked_engines == ("strix", "nuclei")
    assert result.no_completed_run_engines == ("strix",)
    assert result.coverage_rotation_applied is True
    assert result.suppressed_engines == ()
    assert result.to_dict()["no_completed_run_engines"] == ["strix"]
    assert result.may_expand_configuration is False
    assert "configured scanner diversity" in result.reasons["strix"]


def test_positive_security_signal_prevents_negative_yield_rotation():
    result = adapt_scanner_engines(
        ("nuclei", "strix"),
        [_memory("nuclei", successes=1, confidence=0.8, success_rate=1.0)],
        {"by_job_kind": {"nuclei_scan": {"completed": 4}}},
    )

    assert result.selected_engines == ("nuclei", "strix")
    assert result.coverage_rotation_applied is False
    assert result.no_completed_run_engines == ()


def test_no_completed_history_does_not_invent_scanner_rotation():
    result = adapt_scanner_engines(
        ("nuclei", "strix"),
        [],
        {"by_job_kind": {"nuclei_scan": {"completed": 1}}},
    )

    assert result.selected_engines == ("nuclei", "strix")
    assert result.coverage_rotation_applied is False


def test_scanner_rotation_never_overrides_safety_suppression():
    result = adapt_scanner_engines(
        ("nuclei", "strix"),
        [],
        {
            "by_job_kind": {
                "nuclei_scan": {"completed": 4},
                "strix_scan": {"failed": 3, "completed": 0},
            }
        },
    )

    assert result.selected_engines == ("nuclei",)
    assert result.suppressed_engines == ("strix",)
    assert result.coverage_rotation_applied is False


def test_corrupt_worker_counts_do_not_crash_or_change_execution_authority():
    result = adapt_scanner_engines(
        ("nuclei", "strix"),
        [],
        {
            "by_job_kind": {
                "nuclei_scan": {"completed": "invalid"},
                "strix_scan": {"completed": 0},
            }
        },
    )

    assert result.selected_engines == ("nuclei", "strix")
    assert result.suppressed_engines == ()
    assert result.coverage_rotation_applied is False
    assert "operator review" in result.reasons["nuclei"]
    assert result.may_expand_configuration is False
