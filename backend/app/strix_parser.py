from __future__ import annotations

import json
import os
from pathlib import Path

from .main import Campaign, Finding
from .scanner_normalization import (
    dedupe_normalized,
    normalize_strix_item,
    to_campaign_finding,
)


class StrixParserError(RuntimeError):
    pass


def max_strix_json_bytes() -> int:
    raw = os.getenv("XBOW_MAX_STRIX_JSON_BYTES", str(5 * 1024 * 1024))
    try:
        limit = int(raw)
    except ValueError as exc:
        raise StrixParserError("XBOW_MAX_STRIX_JSON_BYTES must be an integer") from exc
    if not 1024 <= limit <= 20 * 1024 * 1024:
        raise StrixParserError(
            "XBOW_MAX_STRIX_JSON_BYTES must be between 1 KiB and 20 MiB"
        )
    return limit


def parse_strix_json(path: str | Path, campaign: Campaign) -> list[Finding]:
    path = Path(path)
    if path.stat().st_size > max_strix_json_bytes():
        raise StrixParserError("Strix vulnerabilities JSON exceeds configured size limit")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = (
            raw.get("vulnerabilities")
            or raw.get("findings")
            or raw.get("results")
            or []
        )
    else:
        raise ValueError("unsupported Strix vulnerabilities JSON")
    if not isinstance(items, list):
        raise ValueError("Strix findings collection must be a list")

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        finding = normalize_strix_item(item, campaign)
        if finding is not None:
            normalized.append(finding)

    return [to_campaign_finding(item) for item in dedupe_normalized(normalized)]
