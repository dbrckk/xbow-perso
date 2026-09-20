from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SURFACE_KINDS = ("asset", "endpoint", "form", "technology", "waf")


@dataclass(frozen=True)
class SurfaceNode:
    kind: str
    value: str
    first_seen_at: str
    last_seen_at: str
    campaign_count: int
    sources: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sources"] = list(self.sources)
        return payload


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def target_memory_max_campaigns() -> int:
    return _bounded_int_env("XBOW_TARGET_MEMORY_MAX_CAMPAIGNS", 50, 1, 500)


def target_memory_max_nodes() -> int:
    return _bounded_int_env("XBOW_TARGET_MEMORY_MAX_NODES", 5000, 100, 20000)


def _target_parts(campaign: dict[str, Any]) -> tuple[str, str]:
    target = dict(campaign.get("target") or {})
    rules = dict(target.get("rules") or {})
    parsed = urlsplit(str(target.get("primary_url") or ""))
    host = (parsed.hostname or "").lower().rstrip(".")
    authorization = str(rules.get("authorization_reference") or "").strip()
    if not host:
        raise ValueError("campaign target has no hostname")
    if not authorization:
        raise ValueError("campaign authorization reference is missing")
    return host, authorization


def target_identity(campaign: dict[str, Any]) -> str:
    """Stable identity for read-only cross-campaign memory.

    Authorization reference is included so two independent programs sharing the
    same host never silently share learned surface state.
    """
    host, authorization = _target_parts(campaign)
    material = f"{host}\x1f{authorization}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _canonical_value(kind: str, value: str) -> str:
    value = str(value).strip()
    if kind == "asset":
        return value.lower().rstrip(".")
    if kind == "endpoint":
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            return value
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return value
        port = f":{parsed.port}" if parsed.port else ""
        netloc = host + port
        path = parsed.path or "/"
        return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))
    if kind in {"technology", "waf"}:
        return " ".join(value.lower().split())
    return " ".join(value.split())


def _campaign_surface(records: list[dict[str, Any]], *, max_nodes: int) -> dict[tuple[str, str], dict[str, Any]]:
    surface: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        kind = str(record.get("kind") or "")
        if kind not in SURFACE_KINDS:
            continue
        value = _canonical_value(kind, str(record.get("value") or ""))
        if not value:
            continue
        key = (kind, value)
        if key not in surface and len(surface) >= max_nodes:
            break
        source = str(record.get("source") or "unknown").strip() or "unknown"
        created_at = str(record.get("created_at") or "")
        item = surface.setdefault(
            key,
            {
                "kind": kind,
                "value": value,
                "first_seen_at": created_at,
                "last_seen_at": created_at,
                "sources": set(),
            },
        )
        item["sources"].add(source)
        if created_at and (not item["first_seen_at"] or created_at < item["first_seen_at"]):
            item["first_seen_at"] = created_at
        if created_at and created_at > item["last_seen_at"]:
            item["last_seen_at"] = created_at
    return surface


def build_target_memory(store: Any, campaign: dict[str, Any]) -> dict[str, Any]:
    """Build bounded read-only target memory from durable campaign observations."""
    campaign_id = str(campaign.get("id") or "")
    if not campaign_id:
        raise ValueError("campaign id required")

    identity = target_identity(campaign)
    host, authorization = _target_parts(campaign)
    max_campaigns = target_memory_max_campaigns()
    max_nodes = target_memory_max_nodes()

    matching: list[dict[str, Any]] = []
    for candidate in store.list_campaigns(limit=min(500, max_campaigns * 5)):
        try:
            if target_identity(candidate) != identity:
                continue
        except ValueError:
            continue
        matching.append(candidate)
        if len(matching) >= max_campaigns:
            break

    matching.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")))

    campaign_surfaces: list[tuple[dict[str, Any], dict[tuple[str, str], dict[str, Any]]]] = []
    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    for item in matching:
        item_id = str(item.get("id") or "")
        records = store.list_observations(item_id)
        surface = _campaign_surface(records, max_nodes=max_nodes)
        campaign_surfaces.append((item, surface))
        for key, node in surface.items():
            if key not in aggregate and len(aggregate) >= max_nodes:
                continue
            agg = aggregate.setdefault(
                key,
                {
                    "kind": node["kind"],
                    "value": node["value"],
                    "first_seen_at": str(item.get("created_at") or node["first_seen_at"]),
                    "last_seen_at": str(item.get("updated_at") or node["last_seen_at"]),
                    "campaign_ids": set(),
                    "sources": set(),
                },
            )
            agg["campaign_ids"].add(item_id)
            agg["sources"].update(node["sources"])
            seen_first = str(item.get("created_at") or node["first_seen_at"])
            seen_last = str(item.get("updated_at") or node["last_seen_at"])
            if seen_first and (not agg["first_seen_at"] or seen_first < agg["first_seen_at"]):
                agg["first_seen_at"] = seen_first
            if seen_last and seen_last > agg["last_seen_at"]:
                agg["last_seen_at"] = seen_last

    nodes = [
        SurfaceNode(
            kind=item["kind"],
            value=item["value"],
            first_seen_at=item["first_seen_at"],
            last_seen_at=item["last_seen_at"],
            campaign_count=len(item["campaign_ids"]),
            sources=tuple(sorted(item["sources"])),
        )
        for item in aggregate.values()
    ]
    nodes.sort(key=lambda item: (item.kind, item.value))

    current_surface: dict[tuple[str, str], dict[str, Any]] = {}
    previous_surface: dict[tuple[str, str], dict[str, Any]] = {}
    previous_campaign: dict[str, Any] | None = None
    for item, surface in campaign_surfaces:
        if str(item.get("id") or "") == campaign_id:
            current_surface = surface
            break
    if not current_surface:
        current_surface = _campaign_surface(store.list_observations(campaign_id), max_nodes=max_nodes)

    earlier = [
        pair
        for pair in campaign_surfaces
        if str(pair[0].get("id") or "") != campaign_id
        and str(pair[0].get("created_at") or "") <= str(campaign.get("created_at") or "")
    ]
    if earlier:
        previous_campaign, previous_surface = earlier[-1]

    current_keys = set(current_surface)
    previous_keys = set(previous_surface)
    added = sorted(current_keys - previous_keys)
    removed = sorted(previous_keys - current_keys)
    persistent = sorted(current_keys & previous_keys)

    by_kind: dict[str, int] = {kind: 0 for kind in SURFACE_KINDS}
    for node in nodes:
        by_kind[node.kind] = by_kind.get(node.kind, 0) + 1

    return {
        "target": {
            "host": host,
            "identity": identity,
            "authorization_reference": authorization,
        },
        "campaign_id": campaign_id,
        "campaigns_considered": len(matching),
        "previous_campaign_id": (
            str(previous_campaign.get("id")) if previous_campaign is not None else None
        ),
        "summary": {
            "nodes": len(nodes),
            "by_kind": by_kind,
            "current_nodes": len(current_keys),
            "previous_nodes": len(previous_keys),
        },
        "delta": {
            "added_count": len(added),
            "removed_count": len(removed),
            "persistent_count": len(persistent),
            "added": [{"kind": kind, "value": value} for kind, value in added[:200]],
            "removed": [{"kind": kind, "value": value} for kind, value in removed[:200]],
            "truncated": len(added) > 200 or len(removed) > 200,
        },
        "nodes": [node.to_dict() for node in nodes],
        "read_only": True,
        "advisory_only": True,
    }
