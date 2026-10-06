from app.differential_quality import DifferentialQuality
from app.repeat_validation_outcome import (
    REPEAT_VALIDATION_OUTCOME_SCHEMA,
    build_repeat_validation_outcome,
)


def _quality(
    *,
    observations=2,
    strong=2,
    weak=0,
    none=0,
    reproducible=True,
    contradictory=False,
    score=0.9,
    false_positive_risk="low",
):
    return DifferentialQuality(
        schema="differential-quality-v1",
        finding_id="f1",
        observation_count=observations,
        strong_observation_count=strong,
        weak_observation_count=weak,
        none_observation_count=none,
        validator_sources=("validator-a", "validator-b"),
        validator_source_count=2,
        parameters=("q",),
        strong_parameters=("q",) if strong else (),
        strong_parameter_consistent=strong > 0,
        marker_reflection_count=strong,
        status_change_count=0,
        body_change_count=max(strong, weak),
        reproducible=reproducible,
        contradictory=contradictory,
        reproducibility_level=(
            "multi_source_repeated" if reproducible else "single"
        ),
        specificity_level="high" if strong else "low",
        quality_score=score,
        false_positive_risk=false_positive_risk,
        independent_validation_required=True,
        exploitability_confirmed=False,
        zero_day_claim=False,
    )


def test_repeat_outcome_waits_for_second_observation():
    result = build_repeat_validation_outcome(
        _quality(observations=1, strong=1, reproducible=False, score=0.6)
    )

    assert result.schema == REPEAT_VALIDATION_OUTCOME_SCHEMA
    assert result.state == "repeat_not_completed"
    assert result.repeat_budget_exhausted is False
    assert result.human_review_required is False
    assert result.exploitability_confirmed is False
    assert result.zero_day_claim is False


def test_two_consistent_strong_observations_are_reproduced_not_confirmed():
    result = build_repeat_validation_outcome(_quality())

    assert result.state == "reproduced_strong_signal"
    assert result.confidence == "high"
    assert result.repeat_budget_exhausted is True
    assert result.human_review_required is True
    assert "strong_signal_reproduced" in result.reasons
    assert result.exploitability_confirmed is False
    assert result.zero_day_claim is False


def test_conflicting_repeat_is_explicitly_contradictory():
    result = build_repeat_validation_outcome(
        _quality(
            strong=1,
            weak=1,
            reproducible=False,
            contradictory=True,
            score=0.45,
            false_positive_risk="high",
        )
    )

    assert result.state == "contradictory"
    assert result.confidence == "low"
    assert result.human_review_required is True
    assert result.repeat_budget_exhausted is True


def test_unreproduced_strong_signal_is_inconclusive():
    result = build_repeat_validation_outcome(
        _quality(
            strong=1,
            none=1,
            reproducible=False,
            contradictory=False,
            score=0.55,
            false_positive_risk="medium",
        )
    )

    assert result.state == "inconclusive"
    assert result.confidence == "medium"
    assert result.human_review_required is True
    assert result.repeat_budget_exhausted is True


def test_two_non_strong_observations_are_not_reproduced():
    result = build_repeat_validation_outcome(
        _quality(
            strong=0,
            weak=1,
            none=1,
            reproducible=False,
            contradictory=False,
            score=0.2,
            false_positive_risk="high",
        )
    )

    assert result.state == "not_reproduced"
    assert result.confidence == "low"
    assert result.repeat_budget_exhausted is True
    assert result.human_review_required is True
