from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .differential_quality import DifferentialQuality


REPEAT_VALIDATION_OUTCOME_SCHEMA = "repeat-validation-outcome-v1"


@dataclass(frozen=True)
class RepeatValidationOutcome:
    schema: str
    finding_id: str
    state: str
    observation_count: int
    confidence: str
    human_review_required: bool
    repeat_budget_exhausted: bool
    reasons: tuple[str, ...]
    exploitability_confirmed: bool
    zero_day_claim: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def build_repeat_validation_outcome(
    quality: DifferentialQuality,
) -> RepeatValidationOutcome:
    observations = max(0, int(quality.observation_count))
    repeat_budget_exhausted = observations >= 2
    reasons: list[str] = []

    if observations < 2:
        state = "repeat_not_completed"
        confidence = "insufficient"
        human_review_required = False
        reasons.append("second_observation_missing")
    elif quality.contradictory:
        state = "contradictory"
        confidence = "low"
        human_review_required = True
        reasons.append("differential_results_conflict")
    elif (
        quality.reproducible
        and quality.strong_observation_count >= 2
        and quality.quality_score >= 0.70
        and quality.false_positive_risk == "low"
    ):
        state = "reproduced_strong_signal"
        confidence = "high"
        human_review_required = True
        reasons.extend(
            (
                "strong_signal_reproduced",
                "automatic_repeat_budget_exhausted",
            )
        )
    elif quality.strong_observation_count >= 1:
        state = "inconclusive"
        confidence = "medium"
        human_review_required = True
        reasons.append("strong_signal_not_cleanly_reproduced")
    else:
        state = "not_reproduced"
        confidence = "low"
        human_review_required = True
        reasons.append("strong_signal_not_observed_on_repeat")

    return RepeatValidationOutcome(
        schema=REPEAT_VALIDATION_OUTCOME_SCHEMA,
        finding_id=quality.finding_id,
        state=state,
        observation_count=observations,
        confidence=confidence,
        human_review_required=human_review_required,
        repeat_budget_exhausted=repeat_budget_exhausted,
        reasons=tuple(reasons),
        exploitability_confirmed=False,
        zero_day_claim=False,
    )
