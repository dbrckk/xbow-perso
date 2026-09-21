from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse


_SOURCE_MAP_RE = re.compile(r"(?://[#@]\s*sourceMappingURL\s*=\s*([^\s*]+))")
_ABSOLUTE_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_PATH_RE = re.compile(r"(?<![A-Za-z0-9])(/(?:api|graphql|v[0-9]+|admin|internal)/[A-Za-z0-9_./?=&%-]*)")
_SECRET_SHAPE_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|authorization)\s*[:=]"
)


def analyze_public_text_response(
    *,
    url: str,
    body: str,
    content_type: str = "",
    max_body_chars: int = 1_000_000,
) -> dict[str, Any]:
    """Extract passive public-response signals without fetching anything.

    The function operates only on response text already collected by an authorized
    campaign. Potential secret values are never returned; only a boolean/count is
    retained.
    """
    text = str(body or "")[:max_body_chars]
    base = str(url)
    origin = urlparse(base)

    source_maps: list[str] = []
    for match in _SOURCE_MAP_RE.findall(text):
        candidate = urljoin(base, match.strip())
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.hostname == origin.hostname:
            source_maps.append(candidate)

    urls = []
    for candidate in _ABSOLUTE_URL_RE.findall(text):
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"}:
            urls.append(candidate)

    paths = _PATH_RE.findall(text)
    secret_shape_count = len(_SECRET_SHAPE_RE.findall(text))

    return {
        "url": base,
        "content_type": str(content_type)[:160],
        "source_map_hints": sorted(set(source_maps))[:50],
        "absolute_url_hints": sorted(set(urls))[:100],
        "endpoint_path_hints": sorted(set(paths))[:100],
        "potential_secret_shape_count": min(secret_shape_count, 1000),
        "potential_secret_values_retained": False,
        "network_requests_performed": 0,
        "advisory_only": True,
        "automatic_execution": False,
        "scope_expansion": False,
    }
