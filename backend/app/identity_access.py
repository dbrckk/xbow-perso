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
    signal: str
    requires_human_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["identities"] = list(self.identities)
        return payload


def build_identity_access_differentials(
    graph: ObservationGraph,
    *,
    limit: int = 50,
) -> list[IdentityAccessDifferential]:
    """Compare bounded browser observations from explicitly named test identities.

    A differential is evidence of different behavior, not proof of broken access
    control. No requests are issued here.
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
        grouped.setdefault(endpoint, {})[identity] = {
            "status": status,
            "digest": digest,
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
        status_values = {value for value in statuses.values() if value is not None}
        digest_values = set(digests.values())

        if len(status_values) > 1:
            signal = "status_divergence"
        elif len(digest_values) > 1:
            signal = "content_divergence"
        else:
            signal = "no_observed_divergence"

        results.append(
            IdentityAccessDifferential(
                endpoint=endpoint,
                identities=identities,
                http_status_by_identity=statuses,
                content_sha256_by_identity=digests,
                signal=signal,
            )
        )

    rank = {
        "status_divergence": 0,
        "content_divergence": 1,
        "no_observed_divergence": 2,
    }
    results.sort(key=lambda item: (rank[item.signal], item.endpoint))
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
            "content_divergence": sum(item.signal == "content_divergence" for item in items),
            "no_observed_divergence": sum(
                item.signal == "no_observed_divergence" for item in items
            ),
        },
        "advisory_only": True,
        "automatic_vulnerability_claim": False,
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
