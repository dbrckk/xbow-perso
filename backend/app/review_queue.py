from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Callable, Literal

from fastapi import APIRouter, Query

from .evidence_chain import build_evidence_chains
from .hypothesis_engine import build_hypotheses
from .hypothesis_memory import summarize_hypothesis_stability
from .knowledge_memory import build_knowledge_snapshot, review_severity_bonus
from .observation_graph import ObservationGraph, load_observation_graph
from .reporting_governance import (
    assess_report_artifact_freshness,
    build_reporting_governance_snapshot,
)

ReviewKind = Literal[
    "validate_finding",
    "review_authorization_surface",
    "review_input_surface",
    "review_form_surface",
    "review_technology_surface",
    "review_protection_surface",
    "review_stale_report",
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
    score_components: dict[str, float] | None = None

    @property
    def task_id(self) -> str:
        identity = json.dumps(
            {
                "schema": "review-task-identity-v1",
                "kind": self.kind,
                "target": self.target,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(identity).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["task_id"] = self.task_id
        payload["evidence_ids"] = list(self.evidence_ids)
        payload["parameter_names"] = list(self.parameter_names)
        payload["score_components"] = dict(self.score_components or {})
        return payload


def build_review_queue(
    graph: ObservationGraph,
    *,
    limit: int = 25,
    scope_checker: Callable[[str], bool] | None = None,
    stability: dict[str, dict[str, Any]] | None = None,
    severities: dict[str, str] | None = None,
    stale_reports: list[dict[str, Any]] | None = None,
) -> list[ReviewTask]:
    """Build a deterministic, bounded and optionally scope-aware review queue."""
    if not 1 <= limit <= 100:
        raise ValueError("review queue limit must be between 1 and 100")

    confidence = {
        item.finding_id: item.score
        for item in build_knowledge_snapshot(graph).finding_confidence
    }
    chains = {item.finding_id: item for item in build_evidence_chains(graph)}
    tasks: list[ReviewTask] = []

    for hypothesis in build_hypotheses(graph, limit=100, scope_checker=scope_checker):
        if hypothesis.kind == "validation_gap":
            graph_finding_id = hypothesis.evidence_ids[0]
            chain = chains.get(graph_finding_id)
            chain_penalty = 0.0 if chain and chain.complete else 0.08
            current_confidence = confidence.get(graph_finding_id, 0.35)
            temporal = (stability or {}).get(graph_finding_id.removeprefix("finding:"), {})
            temporal_state = temporal.get("stability")
            temporal_bonus = 0.0
            temporal_reason = ""
            if temporal_state == "contradictory":
                temporal_bonus = 0.10
                temporal_reason = "; temporal evidence is contradictory"
            elif temporal_state == "evolving":
                temporal_bonus = 0.04
                temporal_reason = "; hypothesis is still evolving"
            finding_id = graph_finding_id.removeprefix("finding:")
            severity = (severities or {}).get(finding_id, "info")
            severity_bonus = review_severity_bonus(severity)
            base_score = 0.75
            confidence_gap = round((1.0 - current_confidence) * 0.17, 4)
            components = {
                "base": base_score,
                "severity": severity_bonus,
                "confidence_gap": confidence_gap,
                "evidence_chain_gap": chain_penalty,
                "temporal_instability": temporal_bonus,
            }
            raw_priority = round(sum(components.values()), 4)
            priority = min(1.0, raw_priority)
            components["raw_total"] = raw_priority
            components["capped_total"] = priority
            tasks.append(
                ReviewTask(
                    kind="validate_finding",
                    target=hypothesis.target,
                    priority=priority,
                    reason="independent validation evidence is incomplete" + temporal_reason,
                    evidence_ids=hypothesis.evidence_ids,
                    score_components=components,
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
        elif hypothesis.kind == "form_surface_review":
            tasks.append(
                ReviewTask(
                    kind="review_form_surface",
                    target=hypothesis.target,
                    priority=0.64,
                    reason="observed form surface requires bounded non-destructive review",
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
        elif hypothesis.kind == "protection_surface_review":
            tasks.append(
                ReviewTask(
                    kind="review_protection_surface",
                    target=hypothesis.target,
                    priority=0.50,
                    reason="observed protection layer should constrain review planning",
                    evidence_ids=hypothesis.evidence_ids,
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

    for report in stale_reports or []:
        if not report.get("stale"):
            continue
        reasons = tuple(str(item) for item in report.get("stale_reasons", ()))
        tasks.append(
            ReviewTask(
                kind="review_stale_report",
                target=str(report.get("artifact_id", "unknown-report")),
                priority=0.92,
                reason=(
                    "generated report governance state is stale; "
                    "human re-review is required"
                    + (f" ({', '.join(reasons)})" if reasons else "")
                ),
                evidence_ids=(),
                score_components={
                    "base": 0.92,
                    "governance_drift": 1.0 if reasons else 0.0,
                    "raw_total": 0.92,
                    "capped_total": 0.92,
                },
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


def review_queue_snapshot(tasks: list[ReviewTask]) -> dict[str, Any]:
    task_ids = sorted(item.task_id for item in tasks)
    canonical = json.dumps(
        {
            "schema": "review-queue-snapshot-v1",
            "task_ids": task_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    by_kind: dict[str, int] = {}
    for item in tasks:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
    return {
        "schema": "review-queue-snapshot-v1",
        "fingerprint": hashlib.sha256(canonical).hexdigest(),
        "task_count": len(tasks),
        "task_ids": task_ids,
        "by_kind": dict(sorted(by_kind.items())),
        "read_only": True,
        "advisory_only": True,
    }


def diff_review_queue_snapshots(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    previous_ids = set(str(item) for item in previous.get("task_ids", ()))
    current_ids = set(str(item) for item in current.get("task_ids", ()))
    added = sorted(current_ids - previous_ids)
    removed = sorted(previous_ids - current_ids)
    unchanged = sorted(previous_ids & current_ids)
    return {
        "schema": "review-queue-diff-v1",
        "previous_fingerprint": previous.get("fingerprint"),
        "current_fingerprint": current.get("fingerprint"),
        "changed": bool(added or removed),
        "added_task_ids": added,
        "removed_task_ids": removed,
        "unchanged_task_ids": unchanged,
        "added_count": len(added),
        "removed_count": len(removed),
        "unchanged_count": len(unchanged),
        "read_only": True,
        "advisory_only": True,
    }




@router.get("/api/campaigns/{campaign_id}/review-queue/history")
def campaign_review_queue_history(
    campaign_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    campaign = assert_campaign_exists(campaign_id)
    rows = storage().list_review_queue_snapshots(campaign.id, limit=limit)
    chronological = list(reversed(rows))
    transitions = [
        diff_review_queue_snapshots(
            chronological[index - 1]["document"],
            chronological[index]["document"],
        )
        for index in range(1, len(chronological))
    ]
    return {
        "campaign_id": campaign.id,
        "schema": "review-queue-history-v1",
        "read_only": True,
        "advisory_only": True,
        "snapshots": rows,
        "transitions": transitions,
        "snapshot_count": len(rows),
        "transition_count": len(transitions),
    }

@router.get("/api/campaigns/{campaign_id}/review-queue")
def campaign_review_queue(campaign_id: str, limit: int = 25):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules
    snapshots = storage().list_hypothesis_snapshots(campaign.id, limit=50)
    stability = {
        item["finding_id"]: item
        for item in summarize_hypothesis_stability(snapshots)
    }
    severities = {str(item.id): str(item.severity) for item in campaign.findings}
    reporting = build_reporting_governance_snapshot(campaign.findings, graph)
    stale_reports: list[dict[str, Any]] = []
    for artifact in storage().list_artifacts(campaign.id):
        if artifact.get("kind") != "report":
            continue
        generated = next(
            (
                event
                for event in reversed(campaign.events)
                if event.get("type") == "report_generated"
                and event.get("artifact_id") == artifact["id"]
            ),
            None,
        )
        stale_reports.append(
            assess_report_artifact_freshness(
                artifact_id=str(artifact["id"]),
                generated_governance_fingerprint=(
                    generated.get("reporting_governance_fingerprint")
                    if generated
                    else None
                ),
                generated_provenance_fingerprint=(
                    generated.get("report_provenance_fingerprint")
                    if generated
                    else None
                ),
                current=reporting,
            )
        )
    tasks = build_review_queue(
        graph,
        limit=limit,
        scope_checker=lambda host: is_host_allowed(host, rules.allowed_targets, rules.denied_targets),
        stability=stability,
        severities=severities,
        stale_reports=stale_reports,
    )
    snapshot = review_queue_snapshot(tasks)
    storage().put_review_queue_snapshot(
        campaign.id,
        snapshot["fingerprint"],
        snapshot,
    )
    return {
        "campaign_id": campaign.id,
        "snapshot": snapshot,
        "tasks": [item.to_dict() for item in tasks],
        "summary": {
            "total": len(tasks),
            "highest_priority": max((item.priority for item in tasks), default=0.0),
            "stale_report_reviews": sum(
                item.kind == "review_stale_report" for item in tasks
            ),
        },
        "read_only": True,
        "advisory_only": True,
        "scope_aware": True,
    }
