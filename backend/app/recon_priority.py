from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from .recon_swarm import ReconTask


_TASK_SIGNALS: dict[str, tuple[str, ...]] = {
    "crawl": ("asset", "endpoint"),
    "map_endpoints": ("endpoint", "asset"),
    "detect_technology": ("technology", "waf"),
    "map_forms": ("form", "endpoint"),
    "browser_observe": ("form", "endpoint", "technology"),
}


_HIGH_VALUE_TASKS: dict[str, tuple[str, ...]] = {
    "alternate-representation-access-control": ("map_endpoints", "browser_observe"),
    "graphql-authorization": ("map_endpoints", "browser_observe"),
    "graphql-data-segregation": ("map_endpoints", "browser_observe"),
    "authentication-state-machine": ("browser_observe", "map_forms"),
    "transaction-reconciliation-invariants": ("browser_observe", "map_forms"),
    "server-side-fetch-boundaries": ("map_forms", "map_endpoints"),
}


def _high_value_task_boost(
    task_kind: str,
    high_value_intelligence: dict[str, Any] | None,
) -> tuple[int, tuple[str, ...]]:
    if not high_value_intelligence:
        return 0, ()
    matched: list[tuple[str, int]] = []
    for raw in list(high_value_intelligence.get("focuses") or [])[:20]:
        family = str(raw.get("family") or "")
        if task_kind not in _HIGH_VALUE_TASKS.get(family, ()):
            continue
        try:
            score = int(raw.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        if score >= 50:
            matched.append((family, score))
    if not matched:
        return 0, ()
    matched.sort(key=lambda item: (-item[1], item[0]))
    boost = min(10, 3 + 2 * len(matched))
    return boost, tuple(item[0] for item in matched[:3])


@dataclass(frozen=True)
class ReconPriorityAdjustment:
    kind: str
    original_priority: int
    effective_priority: int
    boost: int
    diff_boost: int
    history_boost: int
    temporal_boost: int
    confidence_factor: float
    high_value_boost: int
    high_value_families: tuple[str, ...]
    signals: tuple[str, ...]
    historical_signals: tuple[str, ...]
    temporal_signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["high_value_families"] = list(self.high_value_families)
        payload["signals"] = list(self.signals)
        payload["historical_signals"] = list(self.historical_signals)
        payload["temporal_signals"] = list(self.temporal_signals)
        return payload


@dataclass(frozen=True)
class ReconPriorityResult:
    tasks: tuple[ReconTask, ...]
    adjustments: tuple[ReconPriorityAdjustment, ...]
    baseline_available: bool
    changed_surface_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [item.to_dict() for item in self.tasks],
            "adjustments": [item.to_dict() for item in self.adjustments],
            "baseline_available": self.baseline_available,
            "changed_surface_count": self.changed_surface_count,
            "scope_expansion": False,
            "new_tasks_created": False,
            "target_rewrite": False,
            "execution_influence": "ordering_only",
            "bounded": True,
        }


def _signal_counts(surface_diff: dict[str, Any]) -> dict[str, int]:
    summary = dict(surface_diff.get("summary") or {})
    raw = dict(summary.get("counts_by_kind") or {})
    counts: dict[str, int] = {}
    for kind, values in raw.items():
        item = dict(values or {})
        added = max(0, int(item.get("added") or 0))
        removed = max(0, int(item.get("removed") or 0))
        # Newly observed surface is a stronger signal. Removed observations are
        # still useful for a refresh but cannot trigger a new target or task.
        counts[str(kind)] = min(20, added * 2 + removed)
    return counts




def _historical_kind_scores(target_memory: dict[str, Any] | None) -> dict[str, float]:
    if not target_memory:
        return {}
    delta = dict(target_memory.get("delta") or {})
    added = {
        (str(item.get("kind") or ""), str(item.get("value") or ""))
        for item in list(delta.get("added") or [])[:200]
    }
    scores: dict[str, float] = {}
    for raw in list(target_memory.get("nodes") or [])[:20000]:
        kind = str(raw.get("kind") or "")
        value = str(raw.get("value") or "")
        if (kind, value) not in added:
            continue
        try:
            campaign_count = max(1, int(raw.get("campaign_count") or 1))
        except (TypeError, ValueError):
            campaign_count = 1
        # Newly observed nodes (count=1) are the strongest historical novelty
        # signal. Reappearing nodes still contribute, but progressively less.
        novelty = 1.0 / float(campaign_count)
        scores[kind] = min(5.0, scores.get(kind, 0.0) + novelty)
    return scores



_TEMPORAL_CLASS_WEIGHT = {
    "new": 1.0,
    "returning": 0.35,
    "intermittent": 0.15,
    "stable": 0.0,
    "disappeared": 0.0,
    "historical": 0.0,
    "unknown": 0.0,
}


def _temporal_kind_scores(surface_temporal: dict[str, Any] | None) -> dict[str, float]:
    if not surface_temporal:
        return {}
    scores: dict[str, float] = {}
    for raw in list(surface_temporal.get("nodes") or [])[:500]:
        kind = str(raw.get("kind") or "")
        classification = str(raw.get("classification") or "unknown")
        weight = _TEMPORAL_CLASS_WEIGHT.get(classification, 0.0)
        if weight <= 0:
            continue
        try:
            ratio = float(raw.get("presence_ratio") or 0.0)
        except (TypeError, ValueError):
            ratio = 0.0
        ratio = max(0.0, min(1.0, ratio))
        if classification == "new":
            adjusted = weight
        else:
            # Returning/intermittent surface is expected churn; reduce its
            # contribution further as its historical presence rises.
            adjusted = weight * max(0.1, 1.0 - ratio)
        scores[kind] = min(5.0, scores.get(kind, 0.0) + adjusted)
    return scores



def _confidence_kind_scores(surface_confidence: dict[str, Any] | None) -> dict[str, float]:
    if not surface_confidence:
        return {}
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for raw in list(surface_confidence.get("nodes") or [])[:500]:
        kind = str(raw.get("kind") or "")
        if not kind:
            continue
        try:
            score = float(raw.get("confidence") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        totals[kind] = totals.get(kind, 0.0) + score
        counts[kind] = counts.get(kind, 0) + 1
    return {
        kind: totals[kind] / counts[kind]
        for kind in totals
        if counts.get(kind, 0) > 0
    }

def prioritize_recon_tasks(
    tasks: list[ReconTask],
    surface_diff: dict[str, Any],
    target_memory: dict[str, Any] | None = None,
    surface_temporal: dict[str, Any] | None = None,
    surface_confidence: dict[str, Any] | None = None,
    high_value_intelligence: dict[str, Any] | None = None,
) -> ReconPriorityResult:
    """Reorder an already-authorized recon plan using historical change signals.

    This function may only alter priority/reason. It never creates a task,
    changes a target, changes methods, changes request budgets, or broadens scope.
    """
    counts = _signal_counts(surface_diff)
    historical_scores = _historical_kind_scores(target_memory)
    temporal_scores = _temporal_kind_scores(surface_temporal)
    confidence_scores = _confidence_kind_scores(surface_confidence)
    baseline_available = bool(surface_diff.get("baseline_available"))
    changed_surface_count = max(
        0,
        int(dict(surface_diff.get("summary") or {}).get("change_count") or 0),
    )

    adjusted: list[ReconTask] = []
    audit: list[ReconPriorityAdjustment] = []

    for task in tasks:
        signals = _TASK_SIGNALS.get(task.kind, ())
        signal_strength = sum(counts.get(kind, 0) for kind in signals)
        diff_boost = min(15, signal_strength * 2) if baseline_available else 0
        history_strength = sum(historical_scores.get(kind, 0.0) for kind in signals)
        history_boost = min(5, int(round(history_strength))) if baseline_available else 0
        temporal_strength = sum(temporal_scores.get(kind, 0.0) for kind in signals)
        temporal_boost = min(5, int(round(temporal_strength))) if baseline_available else 0
        confidence_values = [
            confidence_scores[kind]
            for kind in signals
            if kind in confidence_scores
        ]
        confidence_factor = (
            max(0.5, min(1.0, sum(confidence_values) / len(confidence_values)))
            if confidence_values
            else 1.0
        )
        high_value_boost, high_value_families = _high_value_task_boost(
            task.kind,
            high_value_intelligence,
        )
        baseline_boost = min(
            20,
            diff_boost + history_boost + temporal_boost,
        )
        raw_boost = min(
            25,
            baseline_boost + high_value_boost,
        )
        boost = min(25, int(round(raw_boost * confidence_factor)))
        effective = min(100, int(task.priority) + boost)
        reason = task.reason
        active = tuple(kind for kind in signals if counts.get(kind, 0) > 0)
        historical_active = tuple(
            kind for kind in signals if historical_scores.get(kind, 0.0) > 0
        )
        temporal_active = tuple(
            kind for kind in signals if temporal_scores.get(kind, 0.0) > 0
        )
        if boost:
            details = []
            if diff_boost:
                details.append(f"diff +{diff_boost}")
            if history_boost:
                details.append(f"history +{history_boost}")
            if temporal_boost:
                details.append(f"temporal +{temporal_boost}")
            if high_value_boost:
                details.append(f"high-value +{high_value_boost}")
            if confidence_factor < 0.999:
                details.append(f"confidence x{confidence_factor:.2f}")
            reason = (
                f"{task.reason}; recon-priority +{boost} "
                f"({'; '.join(details)}"
                + (f"; signals={', '.join(active)}" if active else "")
                + (f"; novelty={', '.join(historical_active)}" if historical_active else "")
                + (f"; temporal={', '.join(temporal_active)}" if temporal_active else "")
                + ")"
            )

        updated = replace(task, priority=effective, reason=reason)
        # Fail closed if any field beyond the intended ordering metadata changed.
        if (
            updated.kind != task.kind
            or updated.agent != task.agent
            or updated.target != task.target
            or updated.max_requests != task.max_requests
            or updated.allowed_methods != task.allowed_methods
            or updated.same_origin_only != task.same_origin_only
            or updated.read_only != task.read_only
        ):
            raise ValueError("recon diff prioritizer attempted to alter task authority")

        adjusted.append(updated)
        audit.append(
            ReconPriorityAdjustment(
                kind=task.kind,
                original_priority=int(task.priority),
                effective_priority=effective,
                boost=boost,
                diff_boost=diff_boost,
                history_boost=history_boost,
                temporal_boost=temporal_boost,
                confidence_factor=round(confidence_factor, 4),
                high_value_boost=high_value_boost,
                high_value_families=high_value_families,
                signals=active,
                historical_signals=historical_active,
                temporal_signals=temporal_active,
            )
        )

    adjusted.sort(key=lambda item: (-item.priority, item.kind, item.agent))
    audit.sort(key=lambda item: (-item.effective_priority, item.kind))

    return ReconPriorityResult(
        tasks=tuple(adjusted),
        adjustments=tuple(audit),
        baseline_available=baseline_available,
        changed_surface_count=changed_surface_count,
    )
