from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter

from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()


@dataclass(frozen=True)
class IdentityAccessDifferential:
    endpoint: str
    identities: tuple[str, ...]
    http_status_by_identity: dict[str, int | None]
    content_sha256_by_identity: dict[str, str]
    structure_sha256_by_identity: dict[str, str]
    structure_metrics_by_identity: dict[str, dict[str, int]]
    signal: str
    priority_score: int
    requires_human_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["identities"] = list(self.identities)
        return payload


def _bounded_structure_metrics(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        name = str(key)[:80]
        if not name:
            continue
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        result[name] = max(0, min(number, 100000))
        if len(result) >= 32:
            break
    return result


def build_identity_access_differentials(
    graph: ObservationGraph,
    *,
    limit: int = 50,
) -> list[IdentityAccessDifferential]:
    """Compare bounded browser observations from explicitly named test identities.

    A differential is evidence of different behavior, not proof of broken access
    control. No requests are issued here. Structure signatures contain only DOM
    element counts, never page text or secret values.
    """
    if not 1 <= limit <= 200:
        raise ValueError("identity differential limit must be between 1 and 200")

    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for item in graph.by_kind("access_surface"):
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        identity = str(metadata.get("identity_label") or "").strip()
        endpoint = str(item.value or "").strip()
        if not identity or not endpoint:
            continue
        status_raw = metadata.get("http_status")
        try:
            status = int(status_raw) if status_raw is not None else None
        except (TypeError, ValueError):
            status = None
        digest = str(metadata.get("content_sha256") or "").strip()
        structure_digest = str(metadata.get("structure_sha256") or "").strip()
        grouped.setdefault(endpoint, {})[identity] = {
            "status": status,
            "digest": digest,
            "structure_digest": structure_digest,
            "structure_metrics": _bounded_structure_metrics(
                metadata.get("structure_metrics")
            ),
        }

    results: list[IdentityAccessDifferential] = []
    for endpoint, observations in grouped.items():
        if len(observations) < 2:
            continue
        identities = tuple(sorted(observations))
        statuses = {
            identity: observations[identity]["status"]
            for identity in identities
        }
        digests = {
            identity: observations[identity]["digest"]
            for identity in identities
            if observations[identity]["digest"]
        }
        structure_digests = {
            identity: observations[identity]["structure_digest"]
            for identity in identities
            if observations[identity]["structure_digest"]
        }
        structure_metrics = {
            identity: observations[identity]["structure_metrics"]
            for identity in identities
            if observations[identity]["structure_metrics"]
        }
        status_values = {value for value in statuses.values() if value is not None}
        digest_values = set(digests.values())
        structure_values = set(structure_digests.values())

        if len(status_values) > 1:
            signal = "status_divergence"
            priority_score = 90
        elif len(structure_values) > 1:
            signal = "structure_divergence"
            priority_score = 75
        elif len(digest_values) > 1:
            signal = "content_divergence"
            priority_score = 45
        else:
            signal = "no_observed_divergence"
            priority_score = 0

        results.append(
            IdentityAccessDifferential(
                endpoint=endpoint,
                identities=identities,
                http_status_by_identity=statuses,
                content_sha256_by_identity=digests,
                structure_sha256_by_identity=structure_digests,
                structure_metrics_by_identity=structure_metrics,
                signal=signal,
                priority_score=priority_score,
            )
        )

    rank = {
        "status_divergence": 0,
        "structure_divergence": 1,
        "content_divergence": 2,
        "no_observed_divergence": 3,
    }
    results.sort(
        key=lambda item: (
            rank[item.signal],
            -item.priority_score,
            item.endpoint,
        )
    )
    return results[:limit]


def summarize_identity_access_differentials(
    graph: ObservationGraph,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    items = build_identity_access_differentials(graph, limit=limit)
    return {
        "items": [item.to_dict() for item in items],
        "summary": {
            "total": len(items),
            "status_divergence": sum(item.signal == "status_divergence" for item in items),
            "structure_divergence": sum(
                item.signal == "structure_divergence" for item in items
            ),
            "content_divergence": sum(item.signal == "content_divergence" for item in items),
            "no_observed_divergence": sum(
                item.signal == "no_observed_divergence" for item in items
            ),
        },
        "advisory_only": True,
        "automatic_vulnerability_claim": False,
        "network_requests_performed": 0,
        "sensitive_content_retained": False,
    }



@router.get("/api/campaigns/{campaign_id}/identity-access-differentials")
def campaign_identity_access_differentials(campaign_id: str, limit: int = 50):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    result = summarize_identity_access_differentials(graph, limit=limit)
    return {
        "campaign_id": campaign.id,
        **result,
    }
