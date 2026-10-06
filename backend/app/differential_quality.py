from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .observation_graph import ObservationGraph


DIFFERENTIAL_QUALITY_SCHEMA = "differential-quality-v1"
_SIGNAL_LEVELS = {"none", "weak", "strong"}


@dataclass(frozen=True)
class DifferentialQuality:
    schema: str
    finding_id: str
    observation_count: int
    strong_observation_count: int
    weak_observation_count: int
    none_observation_count: int
    validator_sources: tuple[str, ...]
    validator_source_count: int
    parameters: tuple[str, ...]
    strong_parameters: tuple[str, ...]
    strong_parameter_consistent: bool
    marker_reflection_count: int
    status_change_count: int
    body_change_count: int
    reproducible: bool
    contradictory: bool
    reproducibility_level: str
    specificity_level: str
    quality_score: float
    false_positive_risk: str
    independent_validation_required: bool
    exploitability_confirmed: bool
    zero_day_claim: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["validator_sources"] = list(self.validator_sources)
        payload["parameters"] = list(self.parameters)
        payload["strong_parameters"] = list(self.strong_parameters)
        return payload


def _finding_id(observation: Any) -> str | None:
    value = observation.metadata.get("finding_id")
    if isinstance(value, str) and value:
        return value
    for parent_id in observation.parent_ids:
        if parent_id.startswith("finding:"):
            return parent_id[len("finding:") :]
    return None


def empty_differential_quality(finding_id: str) -> DifferentialQuality:
    return DifferentialQuality(
        schema=DIFFERENTIAL_QUALITY_SCHEMA,
        finding_id=finding_id,
        observation_count=0,
        strong_observation_count=0,
        weak_observation_count=0,
        none_observation_count=0,
        validator_sources=(),
        validator_source_count=0,
        parameters=(),
        strong_parameters=(),
        strong_parameter_consistent=False,
        marker_reflection_count=0,
        status_change_count=0,
        body_change_count=0,
        reproducible=False,
        contradictory=False,
        reproducibility_level="none",
        specificity_level="none",
        quality_score=0.0,
        false_positive_risk="high",
        independent_validation_required=True,
        exploitability_confirmed=False,
        zero_day_claim=False,
    )


def build_differential_quality(
    graph: ObservationGraph,
) -> dict[str, DifferentialQuality]:
    finding_ids: set[str] = set()
    for observation in graph.by_kind("finding"):
        finding_ids.add(
            observation.id[len("finding:") :]
            if observation.id.startswith("finding:")
            else observation.id
        )

    rows: dict[str, list[Any]] = {}
    for observation in graph.by_kind("validation"):
        finding_id = _finding_id(observation)
        if not finding_id:
            continue
        finding_ids.add(finding_id)
        signal = observation.metadata.get("differential_signal")
        if signal not in _SIGNAL_LEVELS:
            continue
        rows.setdefault(finding_id, []).append(observation)

    result: dict[str, DifferentialQuality] = {}
    for finding_id in sorted(finding_ids):
        observations = rows.get(finding_id, [])
        if not observations:
            result[finding_id] = empty_differential_quality(finding_id)
            continue

        levels = [
            str(item.metadata.get("differential_signal"))
            for item in observations
        ]
        strong = [item for item in observations if item.metadata.get("differential_signal") == "strong"]
        weak_count = sum(level == "weak" for level in levels)
        none_count = sum(level == "none" for level in levels)

        validator_sources = tuple(
            sorted(
                {
                    str(item.source).strip()[:120]
                    for item in observations
                    if str(item.source).strip()
                }
            )
        )
        parameters = tuple(
            sorted(
                {
                    str(item.metadata["differential_parameter"]).strip()[:120]
                    for item in observations
                    if isinstance(item.metadata.get("differential_parameter"), str)
                    and str(item.metadata["differential_parameter"]).strip()
                }
            )
        )
        strong_parameters = tuple(
            sorted(
                {
                    str(item.metadata["differential_parameter"]).strip()[:120]
                    for item in strong
                    if isinstance(item.metadata.get("differential_parameter"), str)
                    and str(item.metadata["differential_parameter"]).strip()
                }
            )
        )
        strong_parameter_consistent = (
            len(strong_parameters) == 1 and bool(strong)
        )

        marker_reflections = sum(
            item.metadata.get("differential_marker_reflected") is True
            for item in observations
        )
        status_changes = sum(
            item.metadata.get("differential_status_changed") is True
            for item in observations
        )
        body_changes = sum(
            item.metadata.get("differential_body_changed") is True
            for item in observations
        )

        signals_by_parameter: dict[str, set[str]] = {}
        for item in observations:
            parameter = item.metadata.get("differential_parameter")
            signal = item.metadata.get("differential_signal")
            if not isinstance(parameter, str) or not parameter.strip():
                continue
            signals_by_parameter.setdefault(parameter.strip(), set()).add(
                str(signal)
            )
        contradictory = any(
            "strong" in signals and bool(signals & {"weak", "none"})
            for signals in signals_by_parameter.values()
        )

        reproducible = len(strong) >= 2 and strong_parameter_consistent
        if reproducible and len(validator_sources) >= 2:
            reproducibility_level = "multi_source_repeated"
        elif reproducible:
            reproducibility_level = "repeated"
        elif strong:
            reproducibility_level = "single"
        else:
            reproducibility_level = "none"

        if marker_reflections:
            specificity_level = "high"
        elif status_changes:
            specificity_level = "medium"
        elif body_changes:
            specificity_level = "low"
        else:
            specificity_level = "none"

        score = 0.0
        if marker_reflections:
            score += 0.45
        elif status_changes:
            score += 0.25
        elif body_changes:
            score += 0.15

        if reproducible:
            score += 0.30
        elif strong:
            score += 0.10

        if len(validator_sources) >= 2:
            score += 0.15
        elif validator_sources:
            score += 0.05

        if contradictory:
            score -= 0.25
        score = round(max(0.0, min(1.0, score)), 4)

        if contradictory or score < 0.35:
            false_positive_risk = "high"
        elif score < 0.70:
            false_positive_risk = "medium"
        else:
            false_positive_risk = "low"

        result[finding_id] = DifferentialQuality(
            schema=DIFFERENTIAL_QUALITY_SCHEMA,
            finding_id=finding_id,
            observation_count=len(observations),
            strong_observation_count=len(strong),
            weak_observation_count=weak_count,
            none_observation_count=none_count,
            validator_sources=validator_sources,
            validator_source_count=len(validator_sources),
            parameters=parameters,
            strong_parameters=strong_parameters,
            strong_parameter_consistent=strong_parameter_consistent,
            marker_reflection_count=marker_reflections,
            status_change_count=status_changes,
            body_change_count=body_changes,
            reproducible=reproducible,
            contradictory=contradictory,
            reproducibility_level=reproducibility_level,
            specificity_level=specificity_level,
            quality_score=score,
            false_positive_risk=false_positive_risk,
            independent_validation_required=True,
            exploitability_confirmed=False,
            zero_day_claim=False,
        )
    return result
