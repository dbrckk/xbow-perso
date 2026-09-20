from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_KIND_WEIGHT = {
    "asset": 24,
    "endpoint": 20,
    "form": 18,
    "technology": 10,
    "waf": 8,
}


@dataclass(frozen=True)
class SurfaceChange:
    direction: str
    kind: str
    value: str
    weight: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "kind": self.kind,
            "value": self.value,
            "weight": self.weight,
            "reason": self.reason,
        }


def _change_reason(direction: str, kind: str) -> str:
    if direction == "added":
        labels = {
            "asset": "nouvel actif observé",
            "endpoint": "nouvel endpoint observé",
            "form": "nouvelle surface de formulaire observée",
            "technology": "nouvelle technologie observée",
            "waf": "nouvelle signature WAF observée",
        }
    else:
        labels = {
            "asset": "actif précédemment observé absent du snapshot courant",
            "endpoint": "endpoint précédemment observé absent du snapshot courant",
            "form": "formulaire précédemment observé absent du snapshot courant",
            "technology": "technologie précédemment observée absente du snapshot courant",
            "waf": "signature WAF précédemment observée absente du snapshot courant",
        }
    return labels.get(kind, "changement de surface observé")


def _priority(score: int, change_count: int) -> str:
    if change_count == 0:
        return "stable"
    if score >= 70:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def build_surface_diff_intelligence(memory: dict[str, Any]) -> dict[str, Any]:
    """Convert target-memory deltas into bounded, read-only review intelligence.

    This output is deliberately advisory. It must not be consumed as scanner
    authorization, scope expansion or an execution admission signal.
    """
    delta = dict(memory.get("delta") or {})
    previous_campaign_id = memory.get("previous_campaign_id")
    added = list(delta.get("added") or [])
    removed = list(delta.get("removed") or [])

    changes: list[SurfaceChange] = []
    counts_by_kind = {kind: {"added": 0, "removed": 0} for kind in _KIND_WEIGHT}

    for direction, items in (("added", added), ("removed", removed)):
        for raw in items[:200]:
            kind = str(raw.get("kind") or "")
            value = str(raw.get("value") or "")
            if kind not in _KIND_WEIGHT or not value:
                continue
            counts_by_kind[kind][direction] += 1
            weight = _KIND_WEIGHT[kind]
            # Missing observations are weaker signals than newly observed surface.
            effective_weight = weight if direction == "added" else max(2, weight // 2)
            changes.append(
                SurfaceChange(
                    direction=direction,
                    kind=kind,
                    value=value,
                    weight=effective_weight,
                    reason=_change_reason(direction, kind),
                )
            )

    changes.sort(key=lambda item: (-item.weight, item.direction, item.kind, item.value))
    raw_score = sum(item.weight for item in changes[:20])
    score = min(100, raw_score)
    priority = _priority(score, len(changes))

    focus = [
        item
        for item in changes
        if item.direction == "added" and item.kind in {"asset", "endpoint", "form"}
    ][:20]

    return {
        "campaign_id": memory.get("campaign_id"),
        "previous_campaign_id": previous_campaign_id,
        "baseline_available": bool(previous_campaign_id),
        "summary": {
            "change_score": score,
            "review_priority": priority,
            "change_count": len(changes),
            "added_count": sum(item["added"] for item in counts_by_kind.values()),
            "removed_count": sum(item["removed"] for item in counts_by_kind.values()),
            "counts_by_kind": counts_by_kind,
        },
        "focus": [
            {
                "kind": item.kind,
                "value": item.value,
                "reason": item.reason,
            }
            for item in focus
        ],
        "changes": [item.to_dict() for item in changes[:100]],
        "truncated": len(changes) > 100 or bool(delta.get("truncated")),
        "read_only": True,
        "advisory_only": True,
        "execution_influence": False,
        "scope_expansion": False,
    }
