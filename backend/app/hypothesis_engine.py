from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from .observation_graph import ObservationGraph

HypothesisKind = Literal[
    "input_surface_review",
    "authorization_surface_review",
    "technology_surface_review",
    "validation_gap",
]
NextAction = Literal["scan", "validate", "stop"]


@dataclass(frozen=True)
class Hypothesis:
    kind: HypothesisKind
    target: str
    reason: str
    confidence: float
    evidence_ids: tuple[str, ...]
    next_action: NextAction

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_ids"] = list(self.evidence_ids)
        return payload


def build_hypotheses(graph: ObservationGraph, *, limit: int = 20) -> list[Hypothesis]:
    """Derive bounded, read-only review hypotheses from existing observations.

    This layer never emits payloads, exploit instructions, shell commands, or new
    network capabilities. It only ranks review opportunities and maps them onto
    action kinds already controlled by the planner/policy layer.
    """
    if not 1 <= limit <= 100:
        raise ValueError("hypothesis limit must be between 1 and 100")

    hypotheses: list[Hypothesis] = []
    validations = graph.by_kind("validation")

    for endpoint in graph.by_kind("endpoint"):
        parsed = urlparse(endpoint.value)
        if parsed.query:
            hypotheses.append(
                Hypothesis(
                    kind="input_surface_review",
                    target=endpoint.value,
                    reason="endpoint exposes query input that merits bounded review",
                    confidence=0.55,
                    evidence_ids=(endpoint.id,),
                    next_action="scan",
                )
            )
        path = parsed.path.lower()
        if any(token in path for token in ("/account", "/profile", "/user", "/admin")):
            hypotheses.append(
                Hypothesis(
                    kind="authorization_surface_review",
                    target=endpoint.value,
                    reason="endpoint path suggests an authorization-sensitive surface",
                    confidence=0.60,
                    evidence_ids=(endpoint.id,),
                    next_action="scan",
                )
            )

    for technology in graph.by_kind("technology"):
        hypotheses.append(
            Hypothesis(
                kind="technology_surface_review",
                target=technology.value,
                reason="observed technology can guide bounded, version-aware review",
                confidence=0.45,
                evidence_ids=(technology.id,),
                next_action="scan",
            )
        )

    for finding in graph.by_kind("finding"):
        observed = [
            validation
            for validation in validations
            if validation.value == "observed"
            and finding.id in validation.parent_ids
            and validation.source != finding.source
        ]
        if not observed:
            hypotheses.append(
                Hypothesis(
                    kind="validation_gap",
                    target=finding.value,
                    reason="finding lacks observed independent validation evidence",
                    confidence=0.90,
                    evidence_ids=(finding.id,),
                    next_action="validate",
                )
            )

    deduped: dict[tuple[str, str], Hypothesis] = {}
    for item in hypotheses:
        key = (item.kind, item.target)
        previous = deduped.get(key)
        if previous is None or item.confidence > previous.confidence:
            deduped[key] = item

    return sorted(
        deduped.values(),
        key=lambda item: (-item.confidence, item.kind, item.target),
    )[:limit]
