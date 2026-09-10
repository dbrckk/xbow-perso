from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from fastapi import APIRouter

from .observation_graph import ObservationGraph, load_observation_graph

router = APIRouter()


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


def build_attack_surface(graph: ObservationGraph) -> dict[str, Any]:
    assets = []
    for item in graph.by_kind("asset"):
        assets.append(
            {
                "id": item.id,
                "host": canonical_host(item.value),
                "source": item.source,
                "parent_ids": list(item.parent_ids),
            }
        )

    endpoints = []
    for item in graph.by_kind("endpoint"):
        normalized = canonical_endpoint(item.value)
        endpoints.append(
            {
                "id": item.id,
                **normalized,
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
            "hosts": dict(sorted(hosts.items())),
            "schemes": dict(sorted(schemes.items())),
            "endpoint_sources": dict(sorted(endpoint_sources.items())),
            "parameter_names": parameter_names,
        },
        "read_only": True,
    }


@router.get("/api/campaigns/{campaign_id}/attack-surface")
def campaign_attack_surface(campaign_id: str):
    from .main import assert_campaign_exists, storage

    campaign = assert_campaign_exists(campaign_id)
    graph = load_observation_graph(storage(), campaign.id)
    return {
        "campaign_id": campaign.id,
        **build_attack_surface(graph),
    }
