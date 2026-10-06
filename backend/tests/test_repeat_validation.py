import pytest

from app.main import Finding
from app.observation_graph import Observation, ObservationGraph
from app.repeat_validation import (
    REPEAT_DIFFERENTIAL_VALIDATION_SCHEMA,
    RepeatValidationConfigError,
    build_repeat_validation_candidates,
    repeat_differential_validation_enabled,
)


def _finding(*, severity="high", cve_ids=None):
    finding = Finding(
        id="f1",
        title="Unknown behavioral candidate",
        severity=severity,
        asset="https://example.test",
        endpoint="https://example.test/search?q=value",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner-a",
    )
    finding.cve_ids = list(cve_ids or [])
    return finding


def _graph(*, signals=("strong",)):
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner-a"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner-a",
            parent_ids=("asset:a",),
        )
    )
    for index, signal in enumerate(signals, start=1):
        graph.add(
            Observation(
                f"validation:{index}",
                "validation",
                "observed",
                f"validator-{index}",
                parent_ids=("finding:f1",),
                metadata={
                    "finding_id": "f1",
                    "differential_signal": signal,
                    "differential_parameter": "q",
                    "differential_marker_reflected": signal == "strong",
                    "differential_status_changed": False,
                    "differential_body_changed": signal != "none",
                },
            )
        )
    return graph


def test_repeat_validation_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv(
        "XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION",
        raising=False,
    )

    assert repeat_differential_validation_enabled() is False
    assert build_repeat_validation_candidates(
        [_finding()],
        _graph(),
        enabled=False,
    ) == []


def test_single_strong_unknown_candidate_gets_exactly_one_repeat_slot():
    candidates = build_repeat_validation_candidates(
        [_finding()],
        _graph(),
        enabled=True,
    )

    assert len(candidates) == 1
    item = candidates[0]
    assert item.schema == REPEAT_DIFFERENTIAL_VALIDATION_SCHEMA
    assert item.finding_id == "f1"
    assert item.next_observation_ordinal == 2
    assert item.specificity_level == "high"
    assert item.non_destructive_only is True
    assert item.exploit_execution_allowed is False
    assert item.independent_validation_required is True


def test_known_cve_is_excluded_from_unknown_repeat_path():
    assert build_repeat_validation_candidates(
        [_finding(cve_ids=["CVE-2026-12345"])],
        _graph(),
        enabled=True,
    ) == []


def test_low_impact_candidate_is_not_automatically_repeated():
    assert build_repeat_validation_candidates(
        [_finding(severity="medium")],
        _graph(),
        enabled=True,
    ) == []


@pytest.mark.parametrize(
    "signals",
    (
        ("strong", "strong"),
        ("strong", "weak"),
        ("strong", "none"),
    ),
)
def test_second_differential_observation_exhausts_repeat_budget(signals):
    assert build_repeat_validation_candidates(
        [_finding()],
        _graph(signals=signals),
        enabled=True,
    ) == []


def test_invalid_repeat_gate_fails_closed(monkeypatch):
    monkeypatch.setenv(
        "XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION",
        "sometimes",
    )

    with pytest.raises(RepeatValidationConfigError, match="must be a boolean"):
        repeat_differential_validation_enabled()
