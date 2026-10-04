from __future__ import annotations

from fnmatch import fnmatch
from urllib.parse import urlparse


def normalize_pattern(pattern: str) -> str:
    value = str(pattern).strip().lower()
    if "://" in value:
        value = (urlparse(value).hostname or value).lower()
    return value.rstrip(".")


def is_host_allowed(
    host: str,
    allowed: list[str],
    denied: list[str],
) -> bool:
    normalized_host = str(host).lower().rstrip(".")
    denied_patterns = [normalize_pattern(item) for item in denied]
    if any(fnmatch(normalized_host, pattern) for pattern in denied_patterns):
        return False
    allowed_patterns = [normalize_pattern(item) for item in allowed]
    return any(
        fnmatch(normalized_host, pattern)
        for pattern in allowed_patterns
    )
