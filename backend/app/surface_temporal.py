from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .target_memory import _campaign_surface, target_identity, target_memory_max_campaigns, target_memory_max_nodes


@dataclass(frozen=True)
class TemporalSurfaceNode:
    kind: str
    value: str
    classification: str
    appearances: int
    campaigns_observed: int
    transitions: int
    presence_ratio: float
    present_now: bool
    present_previous: bool
    first_seen_campaign_id: str | None
    last_seen_campaign_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "classification": self.classification,
            "appearances": self.appearances,
            "campaigns_observed": self.campaigns_observed,
            "transitions": self.transitions,
            "presence_ratio": self.presence_ratio,
            "present_now": self.present_now,
            "present_previous": self.present_previous,
            "first_seen_campaign_id": self.first_seen_campaign_id,
            "last_seen_campaign_id": self.last_seen_campaign_id,
        }


def _classification(presence: list[bool]) -> str:
    if not presence:
        return "unknown"
    current = presence[-1]
    previous = presence[-2] if len(presence) >= 2 else False
    appearances = sum(1 for value in presence if value)
    prior_appearances = sum(1 for value in presence[:-1] if value)
    transitions = sum(
        1
        for before, after in zip(presence, presence[1:])
        if before != after
    )
    ratio = appearances / len(presence)

    if current and appearances == 1:
        return "new"
    if current and not previous and prior_appearances > 0:
        return "returning"
    if not current and previous:
        return "disappeared"
    if transitions >= 2 or (0.2 <= ratio <= 0.8 and appearances > 1):
        return "intermittent"
    if current and ratio >= 0.8:
        return "stable"
    if not current and appearances:
        return "historical"
    return "unknown"


def build_temporal_surface_profile(store: Any, campaign: dict[str, Any]) -> dict[str, Any]:
    """Build bounded temporal surface stability from same-authority campaigns.

    The profile is descriptive only. It does not modify scope, authorization,
    request budgets, task creation or execution admission.
    """
    campaign_id = str(campaign.get("id") or "")
    if not campaign_id:
        raise ValueError("campaign id required")

    identity = target_identity(campaign)
    cutoff = str(campaign.get("created_at") or "")
    max_campaigns = target_memory_max_campaigns()
    max_nodes = target_memory_max_nodes()

    matching: list[dict[str, Any]] = []
    for candidate in store.list_campaigns(limit=min(500, max_campaigns * 5)):
        try:
            if target_identity(candidate) != identity:
                continue
        except ValueError:
            continue
        created = str(candidate.get("created_at") or "")
        if cutoff and created > cutoff:
            continue
        matching.append(candidate)

    matching.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")))
    matching = matching[-max_campaigns:]

    campaign_ids = [str(item.get("id") or "") for item in matching]
    if campaign_id not in campaign_ids:
        matching.append(campaign)
        matching.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")))
        matching = matching[-max_campaigns:]
        campaign_ids = [str(item.get("id") or "") for item in matching]

    surfaces: list[set[tuple[str, str]]] = []
    universe: set[tuple[str, str]] = set()
    for item in matching:
        records = store.list_observations(str(item.get("id") or ""))
        surface = _campaign_surface(records, max_nodes=max_nodes)
        keys = set(surface)
        surfaces.append(keys)
        if len(universe) < max_nodes:
            remaining = max_nodes - len(universe)
            universe.update(sorted(keys - universe)[:remaining])

    nodes: list[TemporalSurfaceNode] = []
    for kind, value in sorted(universe):
        presence = [(kind, value) in surface for surface in surfaces]
        appearances = sum(1 for seen in presence if seen)
        transitions = sum(
            1
            for before, after in zip(presence, presence[1:])
            if before != after
        )
        seen_indexes = [index for index, seen in enumerate(presence) if seen]
        first_id = campaign_ids[seen_indexes[0]] if seen_indexes else None
        last_id = campaign_ids[seen_indexes[-1]] if seen_indexes else None
        nodes.append(
            TemporalSurfaceNode(
                kind=kind,
                value=value,
                classification=_classification(presence),
                appearances=appearances,
                campaigns_observed=len(presence),
                transitions=transitions,
                presence_ratio=round(appearances / len(presence), 4) if presence else 0.0,
                present_now=presence[-1] if presence else False,
                present_previous=presence[-2] if len(presence) >= 2 else False,
                first_seen_campaign_id=first_id,
                last_seen_campaign_id=last_id,
            )
        )

    counts: dict[str, int] = {}
    for node in nodes:
        counts[node.classification] = counts.get(node.classification, 0) + 1

    volatile = sorted(
        [item for item in nodes if item.classification in {"returning", "intermittent", "disappeared"}],
        key=lambda item: (-item.transitions, item.kind, item.value),
    )
    newly_seen = [item for item in nodes if item.classification == "new"]

    return {
        "campaign_id": campaign_id,
        "campaigns_considered": len(matching),
        "campaign_ids": campaign_ids,
        "summary": {
            "nodes": len(nodes),
            "classifications": counts,
            "volatile_count": len(volatile),
            "new_count": len(newly_seen),
        },
        "volatile": [item.to_dict() for item in volatile[:100]],
        "new": [item.to_dict() for item in newly_seen[:100]],
        "nodes": [item.to_dict() for item in nodes[:500]],
        "truncated": len(nodes) > 500 or len(volatile) > 100 or len(newly_seen) > 100,
        "read_only": True,
        "advisory_only": True,
        "execution_influence": False,
        "scope_expansion": False,
    }
