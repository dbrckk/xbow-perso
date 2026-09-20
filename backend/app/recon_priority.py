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


@dataclass(frozen=True)
class ReconPriorityAdjustment:
    kind: str
    original_priority: int
    effective_priority: int
    boost: int
    signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signals"] = list(self.signals)
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


def prioritize_recon_tasks(
    tasks: list[ReconTask],
    surface_diff: dict[str, Any],
) -> ReconPriorityResult:
    """Reorder an already-authorized recon plan using historical change signals.

    This function may only alter priority/reason. It never creates a task,
    changes a target, changes methods, changes request budgets, or broadens scope.
    """
    counts = _signal_counts(surface_diff)
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
        boost = min(15, signal_strength * 2) if baseline_available else 0
        effective = min(100, int(task.priority) + boost)
        reason = task.reason
        if boost:
            active = tuple(kind for kind in signals if counts.get(kind, 0) > 0)
            reason = (
                f"{task.reason}; diff-priority +{boost} "
                f"({', '.join(active)})"
            )
        else:
            active = ()

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
                signals=active,
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
