from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class PlannerLimitConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PlannerLimits:
    max_observations: int = 5000
    max_endpoints: int = 1500
    max_findings: int = 250


def _strict_positive_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise PlannerLimitConfigError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise PlannerLimitConfigError(f"{name} must be between {minimum} and {maximum}")
    return value


def planner_limits() -> PlannerLimits:
    return PlannerLimits(
        max_observations=_strict_positive_int(
            "XBOW_PLANNER_MAX_OBSERVATIONS", 5000, minimum=100, maximum=100000
        ),
        max_endpoints=_strict_positive_int(
            "XBOW_PLANNER_MAX_ENDPOINTS", 1500, minimum=10, maximum=50000
        ),
        max_findings=_strict_positive_int(
            "XBOW_PLANNER_MAX_FINDINGS", 250, minimum=1, maximum=10000
        ),
    )


def planner_limit_violation(graph: Any) -> str | None:
    """Return a non-secret fail-closed reason when autonomous planner bounds are exceeded."""
    limits = planner_limits()
    observations = graph.values()
    endpoints = graph.by_kind("endpoint")
    findings = graph.by_kind("finding")

    if len(observations) > limits.max_observations:
        return (
            f"planner observation limit exceeded "
            f"({len(observations)} > {limits.max_observations})"
        )
    if len(endpoints) > limits.max_endpoints:
        return (
            f"planner endpoint limit exceeded "
            f"({len(endpoints)} > {limits.max_endpoints})"
        )
    if len(findings) > limits.max_findings:
        return (
            f"planner finding limit exceeded "
            f"({len(findings)} > {limits.max_findings})"
        )
    return None
