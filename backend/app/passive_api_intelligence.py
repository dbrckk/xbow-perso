from __future__ import annotations

import json
import re
from typing import Any


_GRAPHQL_OPERATION_RE = re.compile(
    r"\b(query|mutation|subscription)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_GRAPHQL_FIELD_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^{}]*\))?\s*\{")
_OPENAPI_PATH_RE = re.compile(r"^/(?:[^\s{}]+)$")


def analyze_api_schema_text(
    body: str,
    *,
    content_type: str = "",
    max_body_chars: int = 1_000_000,
) -> dict[str, Any]:
    """Extract API/GraphQL structure from text already collected in scope.

    No network activity is performed and no request payload is generated.
    """
    text = str(body or "")[:max_body_chars]
    operations = [
        {"type": kind, "name": name}
        for kind, name in _GRAPHQL_OPERATION_RE.findall(text)
    ][:100]
    graphql_fields = sorted(set(_GRAPHQL_FIELD_RE.findall(text)))[:200]

    openapi_paths: list[str] = []
    openapi_methods: dict[str, list[str]] = {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None

    if isinstance(parsed, dict):
        paths = parsed.get("paths")
        if isinstance(paths, dict):
            for raw_path, definition in list(paths.items())[:500]:
                path = str(raw_path)
                if not _OPENAPI_PATH_RE.match(path):
                    continue
                openapi_paths.append(path)
                if isinstance(definition, dict):
                    methods = sorted({
                        str(method).upper()
                        for method in definition
                        if str(method).lower() in {
                            "get", "post", "put", "patch", "delete", "head", "options"
                        }
                    })
                    if methods:
                        openapi_methods[path] = methods

    return {
        "content_type": str(content_type)[:160],
        "graphql_operation_names": operations,
        "graphql_field_hints": graphql_fields,
        "openapi_paths": sorted(set(openapi_paths))[:500],
        "openapi_methods": openapi_methods,
        "network_requests_performed": 0,
        "request_payloads_generated": 0,
        "advisory_only": True,
        "automatic_execution": False,
        "scope_expansion": False,
    }
