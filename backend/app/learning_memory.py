from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .no_finding_recovery import _asset_matches_origin, _origin
from .observation_graph import ObservationGraph, load_observation_graph
from .scan_result_integrity import canonical_scan_job_id

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


def _target_scoped_evidence_ids(
    graph: ObservationGraph,
    target_url: str,
) -> frozenset[str]:
    """Find evidence tied exclusively to the requested authorized origin."""
    target = _origin(target_url)
    if target is None:
        raise ValueError("target_url must identify an HTTP(S) origin")
    items = {item.id: item for item in graph.values()}
    assets = graph.by_kind("asset")
    approved = {
        item.id
        for item in assets
        if _asset_matches_origin(item.value, target)
    }
    # Unlinked legacy evidence is safe to assign only when the graph
    # identifies exactly one unambiguous asset for this origin.
    legacy_single_asset = len(assets) == 1 and assets[0].id in approved
    accepted: set[str] = set()
    for item in graph.by_kind("evidence"):
        if not item.parent_ids:
            if legacy_single_asset:
                accepted.add(item.id)
            continue
        pending = list(item.parent_ids)
        seen: set[str] = set()
        ancestors: set[str] = set()
        valid = True
        while pending:
            parent_id = pending.pop()
            if parent_id in seen:
                continue
            seen.add(parent_id)
            parent = items.get(parent_id)
            if parent is None:
                valid = False
                break
            if parent.kind == "asset":
                if parent.id not in approved:
                    valid = False
                    break
                ancestors.add(parent.id)
            else:
                pending.extend(parent.parent_ids)
        if valid and ancestors:
            accepted.add(item.id)
    return frozenset(accepted)


def build_learning_memory(
    graph: ObservationGraph,
    *,
    limit: int = 50,
    target_url: str | None = None,
) -> list[TechniqueMemory]:
    """Aggregate safe technique outcomes from existing evidence only.

    Evidence contributes only when it carries an explicit technique and outcome.
    No target interaction, payload generation, or autonomous execution happens here.
    """
    if not 1 <= limit <= 100:
        raise ValueError("learning memory limit must be between 1 and 100")

    scoped_ids = (
        _target_scoped_evidence_ids(graph, target_url)
        if target_url is not None
        else None
    )
    # A reused worker job ID observed on a different origin must not be
    # partially credited through only its convenient in-scope reporter.
    out_of_scope_jobs: set[tuple[str, str]] = set()
    if scoped_ids is not None:
        for item in graph.by_kind("evidence"):
            if item.id in scoped_ids:
                continue
            technique = str(item.metadata.get("technique") or "").strip().lower()
            job_id = canonical_scan_job_id(
                item.metadata.get("job_id")
            )
            if technique and job_id is not None:
                out_of_scope_jobs.add((technique, f"job:{job_id}"))

    # One scanner or validation job may emit multiple evidence observations.
    # Counting each observation as an independent attempt inflates both
    # failure/success rates and technique confidence. Deduplicate only when
    # an explicit valid job ID is available; historical records without a
    # job ID remain independently accountable by observation ID.
    attempts: dict[tuple[str, str], dict[str, set[str]]] = {}
    for item in graph.by_kind("evidence"):
        if scoped_ids is not None and item.id not in scoped_ids:
            continue
        technique = str(item.metadata.get("technique", "")).strip().lower()
        outcome = str(item.metadata.get("outcome", "")).strip().lower()
        if not technique or outcome not in {"success", "failure", "inconclusive"}:
            continue
        raw_job_id = item.metadata.get("job_id")
        job_id = canonical_scan_job_id(raw_job_id)
        if raw_job_id is None:
            identity = f"observation:{item.id}"
        elif job_id is not None:
            identity = f"job:{job_id}"
        else:
            # Invalid job identity cannot establish independent evidence.
            continue
        if (technique, identity) in out_of_scope_jobs:
            continue
        attempt = attempts.setdefault(
            (technique, identity),
            {"outcomes": set(), "sources": set()},
        )
        attempt["outcomes"].add(outcome)
        if str(item.source).strip():
            attempt["sources"].add(str(item.source).strip())

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "attempts": 0,
            "successes": 0,
            "failures": 0,
            "inconclusive": 0,
            "sources": set(),
        }
    )
    for (technique, _identity), attempt in sorted(attempts.items()):
        bucket = buckets[technique]
        bucket["attempts"] += 1
        outcomes = attempt["outcomes"]
        # Contradictory observations from the same job do not confirm
        # either success or failure, regardless of ingestion order.
        outcome = next(iter(outcomes)) if len(outcomes) == 1 else "inconclusive"
        if outcome == "success":
            bucket["successes"] += 1
        elif outcome == "failure":
            bucket["failures"] += 1
        else:
            bucket["inconclusive"] += 1
        if attempt["sources"]:
            # A single job reported by several components is still one
            # origin of execution evidence, not multiple confirmations.
            bucket["sources"].add(min(attempt["sources"]))

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
    job_id = canonical_scan_job_id(job.get("id"))
    if job_id is None:
        raise ValueError("invalid job identity")
    return {
        "type": "worker_outcome",
        "job_id": job_id,
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
    # A single job may emit queued, retry and terminal events. Learning from
    # the event count inflates scanner failures and can suppress a healthy
    # engine. For planning, count the last valid state of each job only.
    final_by_job: dict[tuple[str, str], str] = {}
    valid_events = 0

    for event in events:
        if not isinstance(event, dict) or event.get("type") != "worker_outcome":
            continue
        kind = str(event.get("job_kind") or "")
        status = str(event.get("status") or "")
        job_id = canonical_scan_job_id(event.get("job_id"))
        if (
            kind not in _ALLOWED_JOB_KINDS
            or status not in _ALLOWED_JOB_STATUSES
            or job_id is None
        ):
            continue
        try:
            attempts = int(event.get("attempts") or 0)
        except (ValueError, TypeError):
            continue
        if not 0 <= attempts <= 5:
            continue
        valid_events += 1
        key = (kind, job_id)
        # A completed worker job is terminal. A delayed queued or failed
        # event for the same job cannot retroactively erase proof that the
        # scanner completed successfully. Retries use a new job identity.
        if final_by_job.get(key) != "completed":
            final_by_job[key] = status
        recent.append(
            {
                "job_id": job_id,
                "job_kind": kind,
                "success": bool(event.get("success")),
                "status": status,
                "attempts": attempts,
                "at": event.get("at"),
            }
        )

    for (kind, _job_id), status in final_by_job.items():
        bucket = "requeued" if status == "queued" else status
        totals[bucket] += 1
        by_kind[kind][bucket] += 1

    return {
        "totals": totals,
        "by_job_kind": {key: dict(value) for key, value in sorted(by_kind.items())},
        "recent_outcomes": recent[-recent_limit:],
        "distinct_jobs": len(final_by_job),
        "duplicate_events": valid_events - len(final_by_job),
        "contains_job_payloads": False,
    }
