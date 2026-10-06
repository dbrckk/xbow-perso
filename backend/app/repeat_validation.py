from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from .differential_quality import build_differential_quality
from .vulnerability_intelligence import finding_cve_ids


REPEAT_DIFFERENTIAL_VALIDATION_SCHEMA = "repeat-differential-validation-v1"
_MAX_DIFFERENTIAL_OBSERVATIONS = 2


class RepeatValidationConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepeatValidationCandidate:
    schema: str
    finding_id: str
    next_observation_ordinal: int
    reason: str
    quality_score: float
    specificity_level: str
    non_destructive_only: bool
    exploit_execution_allowed: bool
    independent_validation_required: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def repeat_differential_validation_enabled() -> bool:
    raw = os.getenv("XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION")
    if raw is None:
        return False
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RepeatValidationConfigError(
        "XBOW_ENABLE_REPEAT_DIFFERENTIAL_VALIDATION must be a boolean"
    )


def build_repeat_validation_candidates(
    findings: list[Any],
    graph: Any,
    *,
    enabled: bool,
) -> list[RepeatValidationCandidate]:
    """Select only one-repeat unknown-vulnerability candidates.

    This function performs no network I/O and never confirms exploitability.
    A candidate must have exactly one strong, high-specificity differential
    observation, no CVE identifier, high/critical severity and no contradictory
    evidence. A second differential observation exhausts the automatic repeat
    budget regardless of its outcome.
    """

    if not enabled:
        return []

    quality_by_id = build_differential_quality(graph)
    candidates: list[RepeatValidationCandidate] = []

    for finding in findings:
        finding_id = str(getattr(finding, "id", ""))
        if not finding_id:
            continue
        if str(getattr(finding, "status", "")) != "validation_required":
            continue
        if str(getattr(finding, "severity", "")).lower() not in {
            "high",
            "critical",
        }:
            continue
        if finding_cve_ids(finding):
            continue

        quality = quality_by_id.get(finding_id)
        if quality is None:
            continue
        if quality.observation_count >= _MAX_DIFFERENTIAL_OBSERVATIONS:
            continue
        if (
            quality.strong_observation_count != 1
            or quality.reproducible
            or quality.contradictory
            or quality.specificity_level != "high"
        ):
            continue

        candidates.append(
            RepeatValidationCandidate(
                schema=REPEAT_DIFFERENTIAL_VALIDATION_SCHEMA,
                finding_id=finding_id,
                next_observation_ordinal=quality.observation_count + 1,
                reason="single_strong_unknown_differential_requires_repeat",
                quality_score=quality.quality_score,
                specificity_level=quality.specificity_level,
                non_destructive_only=True,
                exploit_execution_allowed=False,
                independent_validation_required=True,
            )
        )

    return sorted(
        candidates,
        key=lambda item: (-item.quality_score, item.finding_id),
    )
