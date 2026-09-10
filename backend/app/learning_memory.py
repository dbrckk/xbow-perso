from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()


@dataclass(frozen=True)
class TechniqueMemory:
    technique: str
    attempts: int
    successes: int
    failures: int
    inconclusive: int
    success_rate: float
    confidence: float
    source_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_learning_memory(graph: ObservationGraph, *, limit: int = 50) -> list[TechniqueMemory]:
    """Aggregate safe technique outcomes from existing evidence only.

    Evidence contributes only when it carries an explicit technique and outcome.
    No target interaction, payload generation, or autonomous execution happens here.
    """
    if not 1 <= limit <= 100:
        raise ValueError("learning memory limit must be between 1 and 100")

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "attempts": 0,
            "successes": 0,
            "failures": 0,
            "inconclusive": 0,
            "sources": set(),
        }
    )

    for item in graph.by_kind("evidence"):
        technique = str(item.metadata.get("technique", "")).strip().lower()
        outcome = str(item.metadata.get("outcome", "")).strip().lower()
        if not technique or outcome not in {"success", "failure", "inconclusive"}:
            continue
        bucket = buckets[technique]
        bucket["attempts"] += 1
        bucket["sources"].add(item.source)
        if outcome == "success":
            bucket["successes"] += 1
        elif outcome == "failure":
            bucket["failures"] += 1
        else:
            bucket["inconclusive"] += 1

    memories: list[TechniqueMemory] = []
    for technique, bucket in buckets.items():
        attempts = int(bucket["attempts"])
        successes = int(bucket["successes"])
        failures = int(bucket["failures"])
        conclusive = successes + failures
        success_rate = round(successes / conclusive, 4) if conclusive else 0.0
        confidence = round(min(1.0, conclusive / 5) * min(1.0, len(bucket["sources"]) / 2), 4)
        memories.append(
            TechniqueMemory(
                technique=technique,
                attempts=attempts,
                successes=successes,
                failures=failures,
                inconclusive=int(bucket["inconclusive"]),
                success_rate=success_rate,
                confidence=confidence,
                source_count=len(bucket["sources"]),
            )
        )

    return sorted(
        memories,
        key=lambda item: (-item.confidence, -item.success_rate, -item.attempts, item.technique),
    )[:limit]


@router.get("/api/campaigns/{campaign_id}/learning-memory")
def campaign_learning_memory(campaign_id: str, limit: int = 50):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    memories = build_learning_memory(graph, limit=limit)
    return {
        "campaign_id": campaign.id,
        "techniques": [item.to_dict() for item in memories],
        "summary": {
            "total": len(memories),
            "attempts": sum(item.attempts for item in memories),
            "successes": sum(item.successes for item in memories),
            "failures": sum(item.failures for item in memories),
        },
        "read_only": True,
        "evidence_backed": True,
    }
