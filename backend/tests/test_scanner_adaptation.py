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


def test_adaptation_suppresses_repeatedly_failing_engine_when_alternative_exists():
    result = adapt_scanner_engines(
        ("strix", "nuclei"),
        [_memory("nuclei", failures=2, confidence=0.8, success_rate=0.0)],
        {},
    )

    assert result.selected_engines == ("strix",)
    assert result.suppressed_engines == ("nuclei",)
    assert "repeated scanner failures" in result.reasons["nuclei"]


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
