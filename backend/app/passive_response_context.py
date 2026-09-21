from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .observation_graph import ObservationGraph
from .passive_response_intelligence import analyze_public_text_response


def build_passive_response_context(
    graph: ObservationGraph,
    *,
    scope_checker,
    limit: int = 50,
) -> dict[str, Any]:
    """Analyze already-observed public text bodies without making new requests."""
    analyses: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in graph.values():
        if len(analyses) >= limit:
            break
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        body = metadata.get("response_body")
        url = str(metadata.get("url") or item.value or "")
        if not isinstance(body, str) or not body or not url.startswith(("http://", "https://")):
            continue
        host = (urlparse(url).hostname or "").lower()
        if not host or not scope_checker(host) or url in seen:
            continue
        seen.add(url)
        analyses.append(
            analyze_public_text_response(
                url=url,
                body=body,
                content_type=str(metadata.get("content_type") or ""),
            )
        )

    return {
        "responses_analyzed": len(analyses),
        "source_map_hints": sorted({
            hint for result in analyses for hint in result["source_map_hints"]
        })[:100],
        "endpoint_path_hints": sorted({
            hint for result in analyses for hint in result["endpoint_path_hints"]
        })[:200],
        "potential_secret_shape_count": sum(
            int(result["potential_secret_shape_count"]) for result in analyses
        ),
        "potential_secret_values_retained": False,
        "network_requests_performed": 0,
        "advisory_only": True,
        "automatic_execution": False,
        "scope_expansion": False,
    }
