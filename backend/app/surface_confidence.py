from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SurfaceConfidenceNode:
    kind: str
    value: str
    confidence: float
    grade: str
    source_count: int
    campaign_count: int
    presence_ratio: float
    temporal_classification: str
    rationale: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "confidence": self.confidence,
            "grade": self.grade,
            "source_count": self.source_count,
            "campaign_count": self.campaign_count,
            "presence_ratio": self.presence_ratio,
            "temporal_classification": self.temporal_classification,
            "rationale": list(self.rationale),
        }


def _grade(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.60:
        return "medium"
    return "low"


def _temporal_weight(classification: str) -> float:
    return {
        "stable": 1.0,
        "returning": 0.78,
        "intermittent": 0.58,
        "new": 0.52,
        "disappeared": 0.35,
        "historical": 0.30,
        "unknown": 0.25,
    }.get(classification, 0.25)


def build_surface_confidence(
    target_memory: dict[str, Any],
    surface_temporal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score observation reliability from corroboration and temporal persistence.

    Confidence is descriptive only. It never changes scope, authorization,
    request budgets, task creation, or execution admission.
    """
    temporal_by_key = {
        (str(item.get("kind") or ""), str(item.get("value") or "")): item
        for item in list((surface_temporal or {}).get("nodes") or [])[:500]
    }

    nodes: list[SurfaceConfidenceNode] = []
    for raw in list(target_memory.get("nodes") or [])[:5000]:
        kind = str(raw.get("kind") or "")
        value = str(raw.get("value") or "")
        if not kind or not value:
            continue
        sources = sorted({str(item) for item in list(raw.get("sources") or []) if str(item)})
        try:
            campaign_count = max(1, int(raw.get("campaign_count") or 1))
        except (TypeError, ValueError):
            campaign_count = 1

        temporal = temporal_by_key.get((kind, value), {})
        classification = str(temporal.get("classification") or "unknown")
        try:
            presence_ratio = float(temporal.get("presence_ratio") or 0.0)
        except (TypeError, ValueError):
            presence_ratio = 0.0
        presence_ratio = max(0.0, min(1.0, presence_ratio))

        source_component = min(1.0, len(sources) / 3.0)
        campaign_component = min(1.0, campaign_count / 4.0)
        persistence_component = max(presence_ratio, _temporal_weight(classification))

        score = (
            0.45 * source_component
            + 0.35 * campaign_component
            + 0.20 * persistence_component
        )
        score = round(max(0.0, min(1.0, score)), 4)

        rationale = [
            f"sources={len(sources)}",
            f"campaigns={campaign_count}",
            f"temporal={classification}",
            f"presence={round(presence_ratio * 100)}%",
        ]

        nodes.append(
            SurfaceConfidenceNode(
                kind=kind,
                value=value,
                confidence=score,
                grade=_grade(score),
                source_count=len(sources),
                campaign_count=campaign_count,
                presence_ratio=round(presence_ratio, 4),
                temporal_classification=classification,
                rationale=tuple(rationale),
            )
        )

    nodes.sort(key=lambda item: (-item.confidence, item.kind, item.value))
    grades = {"high": 0, "medium": 0, "low": 0}
    for node in nodes:
        grades[node.grade] += 1

    return {
        "campaign_id": target_memory.get("campaign_id"),
        "summary": {
            "nodes": len(nodes),
            "high": grades["high"],
            "medium": grades["medium"],
            "low": grades["low"],
            "average_confidence": (
                round(sum(item.confidence for item in nodes) / len(nodes), 4)
                if nodes
                else 0.0
            ),
        },
        "top": [item.to_dict() for item in nodes[:50]],
        "low_confidence": [
            item.to_dict()
            for item in sorted(
                (node for node in nodes if node.grade == "low"),
                key=lambda item: (item.confidence, item.kind, item.value),
            )[:50]
        ],
        "nodes": [item.to_dict() for item in nodes[:500]],
        "truncated": len(nodes) > 500,
        "read_only": True,
        "advisory_only": True,
        "execution_influence": False,
        "scope_expansion": False,
    }
