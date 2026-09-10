from __future__ import annotations

from collections import Counter
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from fastapi import APIRouter

from .hypothesis_engine import router as hypothesis_router
from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()
router.routes.extend(hypothesis_router.routes)


def canonical_host(value: str) -> str:
    parsed = urlsplit(value if "://" in value else f"//{value}")
    host = (parsed.hostname or value).strip().lower().rstrip(".")
    return host


def canonical_endpoint(value: str) -> dict[str, Any]:
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError:
        port = None
        valid = False
        error = "invalid_port"
    else:
        valid = bool(scheme and host)
        error = None if valid else "missing_scheme_or_host"

    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    path = parsed.path or "/"
    canonical_url = urlunsplit((scheme, netloc, path, "", "")) if valid else ""
    parameter_names = sorted({key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)})
    return {
        "url": canonical_url,
        "scheme": scheme,
        "host": host,
        "path": path,
        "parameter_names": parameter_names,
        "valid": valid,
        "error": error,
    }


def build_attack_surface(
    graph: ObservationGraph,
    *,
    scope_checker: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    asset_observations = graph.by_kind("asset")
    asset_hosts = {item.id: canonical_host(item.value) for item in asset_observations}

    assets = []
    for item in asset_observations:
        host = asset_hosts[item.id]
        assets.append(
            {
                "id": item.id,
                "host": host,
                "in_scope": scope_checker(host) if scope_checker and host else None,
                "source": item.source,
                "parent_ids": list(item.parent_ids),
            }
        )

    endpoints = []
    for item in graph.by_kind("endpoint"):
        normalized = canonical_endpoint(item.value)
        asset_parent_ids = sorted(parent for parent in item.parent_ids if parent in asset_hosts)
        parent_hosts = sorted({asset_hosts[parent] for parent in asset_parent_ids})
        host = normalized["host"]
        endpoints.append(
            {
                "id": item.id,
                **normalized,
                "in_scope": scope_checker(host) if scope_checker and normalized["valid"] else None,
                "asset_parent_ids": asset_parent_ids,
                "asset_parent_hosts": parent_hosts,
                "host_asset_mismatch": bool(parent_hosts and host not in parent_hosts),
                "source": item.source,
                "parent_ids": list(item.parent_ids),
            }
        )

    technologies = [
        {
            "id": item.id,
            "name": item.value,
            "source": item.source,
            "parent_ids": list(item.parent_ids),
        }
        for item in graph.by_kind("technology")
    ]

    valid_endpoints = [item for item in endpoints if item["valid"]]
    hosts = Counter(item["host"] for item in valid_endpoints if item["host"])
    schemes = Counter(item["scheme"] for item in valid_endpoints if item["scheme"])
    parameter_names = sorted({name for item in valid_endpoints for name in item["parameter_names"]})
    unique_urls = {item["url"] for item in valid_endpoints}
    endpoint_sources = Counter(item["source"] for item in valid_endpoints)
    orphan_endpoints = [item for item in endpoints if not item["asset_parent_ids"]]
    host_asset_mismatches = [item for item in valid_endpoints if item["host_asset_mismatch"]]

    scoped_assets = [item for item in assets if item["in_scope"] is not None]
    scoped_endpoints = [item for item in valid_endpoints if item["in_scope"] is not None]

    return {
        "assets": sorted(assets, key=lambda item: (item["host"], item["id"])),
        "endpoints": sorted(endpoints, key=lambda item: (not item["valid"], item["url"], item["id"])),
        "technologies": sorted(technologies, key=lambda item: (item["name"].lower(), item["id"])),
        "summary": {
            "asset_count": len(assets),
            "endpoint_count": len(endpoints),
            "valid_endpoint_count": len(valid_endpoints),
            "invalid_endpoint_count": len(endpoints) - len(valid_endpoints),
            "unique_endpoint_count": len(unique_urls),
            "duplicate_endpoint_count": max(0, len(valid_endpoints) - len(unique_urls)),
            "technology_count": len(technologies),
            "orphan_endpoint_count": len(orphan_endpoints),
            "host_asset_mismatch_count": len(host_asset_mismatches),
            "in_scope_asset_count": sum(item["in_scope"] is True for item in scoped_assets),
            "out_of_scope_asset_count": sum(item["in_scope"] is False for item in scoped_assets),
            "in_scope_endpoint_count": sum(item["in_scope"] is True for item in scoped_endpoints),
            "out_of_scope_endpoint_count": sum(item["in_scope"] is False for item in scoped_endpoints),
            "hosts": dict(sorted(hosts.items())),
            "schemes": dict(sorted(schemes.items())),
            "endpoint_sources": dict(sorted(endpoint_sources.items())),
            "parameter_names": parameter_names,
        },
        "read_only": True,
    }


@router.get("/api/campaigns/{campaign_id}/attack-surface")
def campaign_attack_surface(campaign_id: str):
    from .main import assert_campaign_exists, is_host_allowed, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    rules = campaign.target.rules
    surface = build_attack_surface(
        graph,
        scope_checker=lambda host: is_host_allowed(host, rules.allowed_targets, rules.denied_targets),
    )
    return {
        "campaign_id": campaign.id,
        **surface,
    }
