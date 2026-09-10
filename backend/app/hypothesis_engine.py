from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from fastapi import APIRouter

from .evidence_chain import router as evidence_chain_router
from .observation_graph import ObservationGraph, load_observation_graph
from .validation_state import analyze_validation_state

HypothesisKind = Literal[
    "input_surface_review",
    "authorization_surface_review",
    "technology_surface_review",
    "validation_gap",
]
NextAction = Literal["scan", "validate", "stop"]

router = APIRouter()
router.routes.extend(evidence_chain_router.routes)


@dataclass(frozen=True)
class Hypothesis:
    kind: HypothesisKind
    target: str
    reason: str
    confidence: float
    evidence_ids: tuple[str, ...]
    next_action: NextAction
    parameter_names: tuple[str, ...] = ()
    dependency_depth: int = 0
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_ids"] = list(self.evidence_ids)
        payload["parameter_names"] = list(self.parameter_names)
        return payload


def _safe_endpoint(value: str) -> tuple[str, tuple[str, ...]]:
    """Return an endpoint representation that never exposes query values/fragments."""
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    safe_url = urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", ""))
    parameter_names = tuple(sorted({key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}))
    return safe_url, parameter_names


def build_hypotheses(graph: ObservationGraph, *, limit: int = 20) -> list[Hypothesis]:
    """Derive bounded, read-only review hypotheses from existing observations.

    This layer never emits payloads, exploit instructions, shell commands, or new
    network capabilities. It only ranks review opportunities and maps them onto
    action kinds already controlled by the planner/policy layer.
    """
    if not 1 <= limit <= 100:
        raise ValueError("hypothesis limit must be between 1 and 100")

    hypotheses: list[Hypothesis] = []
    validation_state = analyze_validation_state(graph)

    for endpoint in graph.by_kind("endpoint"):
        safe_target, parameter_names = _safe_endpoint(endpoint.value)
        path = urlsplit(endpoint.value).path.lower()
        if parameter_names:
            hypotheses.append(
                Hypothesis(
                    kind="input_surface_review",
                    target=safe_target,
                    reason="endpoint exposes named query inputs that merit bounded review",
                    confidence=0.55,
                    evidence_ids=(endpoint.id,),
                    next_action="scan",
                    parameter_names=parameter_names,
                    dependency_depth=len(endpoint.parent_ids),
                )
            )
        if any(token in path for token in ("/account", "/profile", "/user", "/admin")):
            hypotheses.append(
                Hypothesis(
                    kind="authorization_surface_review",
                    target=safe_target,
                    reason="endpoint path suggests an authorization-sensitive surface",
                    confidence=0.60,
                    evidence_ids=(endpoint.id,),
                    next_action="scan",
                    parameter_names=parameter_names,
                    dependency_depth=len(endpoint.parent_ids),
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
                dependency_depth=len(technology.parent_ids),
            )
        )

    for finding in graph.by_kind("finding"):
        if finding.id not in validation_state.observed_independent_finding_ids:
            hypotheses.append(
                Hypothesis(
                    kind="validation_gap",
                    target=finding.value,
                    reason="finding lacks observed independent validation evidence",
                    confidence=0.90,
                    evidence_ids=(finding.id,),
                    next_action="validate",
                    dependency_depth=len(finding.parent_ids),
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


@router.get("/api/campaigns/{campaign_id}/hypotheses")
def campaign_hypotheses(campaign_id: str, limit: int = 20):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    hypotheses = build_hypotheses(graph, limit=limit)
    counts: dict[str, int] = {}
    for item in hypotheses:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return {
        "campaign_id": campaign.id,
        "hypotheses": [item.to_dict() for item in hypotheses],
        "summary": {
            "total": len(hypotheses),
            "by_kind": dict(sorted(counts.items())),
        },
        "read_only": True,
        "safe_validation_only": True,
    }
