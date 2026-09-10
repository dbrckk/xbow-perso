from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from fastapi import APIRouter

from .evidence_chain import build_evidence_chains
from .hypothesis_engine import build_hypotheses
from .knowledge_memory import build_knowledge_snapshot
from .observation_graph import ObservationGraph, load_observation_graph

ReviewKind = Literal[
    "validate_finding",
    "review_authorization_surface",
    "review_input_surface",
    "review_technology_surface",
]

router = APIRouter()


@dataclass(frozen=True)
class ReviewTask:
    kind: ReviewKind
    target: str
    priority: float
    reason: str
    evidence_ids: tuple[str, ...]
    parameter_names: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_ids"] = list(self.evidence_ids)
        payload["parameter_names"] = list(self.parameter_names)
        return payload


def build_review_queue(graph: ObservationGraph, *, limit: int = 25) -> list[ReviewTask]:
    """Build a deterministic, bounded queue of safe review work.

    Tasks are advisory only. They contain no payloads or executable instructions,
    and they do not enqueue jobs or perform network requests.
    """
    if not 1 <= limit <= 100:
        raise ValueError("review queue limit must be between 1 and 100")

    confidence = {
        item.finding_id: item.score
        for item in build_knowledge_snapshot(graph).finding_confidence
    }
    chains = {item.finding_id: item for item in build_evidence_chains(graph)}
    tasks: list[ReviewTask] = []

    for hypothesis in build_hypotheses(graph, limit=100):
        if hypothesis.kind == "validation_gap":
            chain = chains.get(hypothesis.target)
            chain_penalty = 0.0 if chain and chain.complete else 0.08
            current_confidence = confidence.get(hypothesis.target, 0.35)
            priority = min(1.0, round(0.75 + (1.0 - current_confidence) * 0.17 + chain_penalty, 4))
            tasks.append(
                ReviewTask(
                    kind="validate_finding",
                    target=hypothesis.target,
                    priority=priority,
                    reason="independent validation evidence is incomplete",
                    evidence_ids=hypothesis.evidence_ids,
                )
            )
        elif hypothesis.kind == "authorization_surface_review":
            tasks.append(
                ReviewTask(
                    kind="review_authorization_surface",
                    target=hypothesis.target,
                    priority=0.68,
                    reason="authorization-sensitive surface requires bounded review",
                    evidence_ids=hypothesis.evidence_ids,
                    parameter_names=hypothesis.parameter_names,
                )
            )
        elif hypothesis.kind == "input_surface_review":
            tasks.append(
                ReviewTask(
                    kind="review_input_surface",
                    target=hypothesis.target,
                    priority=0.62,
                    reason="named input surface requires bounded review",
                    evidence_ids=hypothesis.evidence_ids,
                    parameter_names=hypothesis.parameter_names,
                )
            )
        elif hypothesis.kind == "technology_surface_review":
            tasks.append(
                ReviewTask(
                    kind="review_technology_surface",
                    target=hypothesis.target,
                    priority=0.45,
                    reason="observed technology requires contextual review",
                    evidence_ids=hypothesis.evidence_ids,
                )
            )

    deduped: dict[tuple[str, str], ReviewTask] = {}
    for task in tasks:
        key = (task.kind, task.target)
        previous = deduped.get(key)
        if previous is None or task.priority > previous.priority:
            deduped[key] = task

    return sorted(
        deduped.values(),
        key=lambda item: (-item.priority, item.kind, item.target),
    )[:limit]


@router.get("/api/campaigns/{campaign_id}/review-queue")
def campaign_review_queue(campaign_id: str, limit: int = 25):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    tasks = build_review_queue(graph, limit=limit)
    return {
        "campaign_id": campaign.id,
        "tasks": [item.to_dict() for item in tasks],
        "summary": {
            "total": len(tasks),
            "highest_priority": max((item.priority for item in tasks), default=0.0),
        },
        "read_only": True,
        "advisory_only": True,
    }
