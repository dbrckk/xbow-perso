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
        "worker_outcomes": summarize_worker_outcomes(campaign.events),
        "read_only": True,
        "evidence_backed": True,
    }


_ALLOWED_JOB_KINDS = {
    "strix_scan",
    "nuclei_scan",
    "independent_validation",
    "browser_flow",
    "recon_task",
    "report",
}
_ALLOWED_JOB_STATUSES = {"queued", "completed", "failed", "cancelled"}


def worker_outcome_event(job: dict[str, Any], *, success: bool, status: str) -> dict[str, Any]:
    """Build a bounded learning event without persisting job payloads or errors."""
    kind = str(job.get("kind") or "")
    if kind not in _ALLOWED_JOB_KINDS:
        raise ValueError("unsupported job kind")
    if status not in _ALLOWED_JOB_STATUSES:
        raise ValueError("unsupported job status")
    attempts = int(job.get("attempts") or 0)
    if not 0 <= attempts <= 5:
        raise ValueError("invalid job attempts")
    return {
        "type": "worker_outcome",
        "job_id": str(job["id"]),
        "job_kind": kind,
        "success": bool(success),
        "status": status,
        "attempts": attempts,
    }


def summarize_worker_outcomes(
    events: list[dict[str, Any]], *, recent_limit: int = 50
) -> dict[str, Any]:
    if not 1 <= recent_limit <= 200:
        raise ValueError("recent_limit must be between 1 and 200")

    totals = {"completed": 0, "failed": 0, "cancelled": 0, "requeued": 0}
    by_kind: dict[str, dict[str, int]] = defaultdict(
        lambda: {"completed": 0, "failed": 0, "cancelled": 0, "requeued": 0}
    )
    recent: list[dict[str, Any]] = []

    for event in events:
        if event.get("type") != "worker_outcome":
            continue
        kind = str(event.get("job_kind") or "")
        status = str(event.get("status") or "")
        if kind not in _ALLOWED_JOB_KINDS or status not in _ALLOWED_JOB_STATUSES:
            continue
        bucket = "requeued" if status == "queued" else status
        totals[bucket] += 1
        by_kind[kind][bucket] += 1
        recent.append(
            {
                "job_id": str(event.get("job_id") or ""),
                "job_kind": kind,
                "success": bool(event.get("success")),
                "status": status,
                "attempts": int(event.get("attempts") or 0),
                "at": event.get("at"),
            }
        )

    return {
        "totals": totals,
        "by_job_kind": {key: dict(value) for key, value in sorted(by_kind.items())},
        "recent_outcomes": recent[-recent_limit:],
        "contains_job_payloads": False,
    }
