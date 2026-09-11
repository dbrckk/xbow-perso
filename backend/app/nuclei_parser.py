from __future__ import annotations

import json
import os
from pathlib import Path

from .main import Campaign, Finding
from .scanner_normalization import (
    dedupe_normalized,
    normalize_nuclei_item,
    to_campaign_finding,
)


class NucleiParserError(RuntimeError):
    pass


def _max_nuclei_jsonl_bytes() -> int:
    raw = os.getenv("XBOW_MAX_NUCLEI_JSONL_BYTES", str(10 * 1024 * 1024))
    try:
        limit = int(raw)
    except ValueError as exc:
        raise NucleiParserError("XBOW_MAX_NUCLEI_JSONL_BYTES must be an integer") from exc
    if not 1024 <= limit <= 50 * 1024 * 1024:
        raise NucleiParserError(
            "XBOW_MAX_NUCLEI_JSONL_BYTES must be between 1 KiB and 50 MiB"
        )
    return limit


def parse_nuclei_jsonl(path: str | Path, campaign: Campaign) -> list[Finding]:
    path = Path(path)
    if path.stat().st_size > _max_nuclei_jsonl_bytes():
        raise NucleiParserError("Nuclei JSONL exceeds configured size limit")

    normalized = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid Nuclei JSONL at line {line_number}"
                ) from exc
            if not isinstance(item, dict):
                continue
            finding = normalize_nuclei_item(item, campaign)
            if finding is not None:
                normalized.append(finding)

    return [to_campaign_finding(item) for item in dedupe_normalized(normalized)]
