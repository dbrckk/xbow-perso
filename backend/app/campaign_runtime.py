from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CampaignRuntimeLimit:
    max_runtime_seconds: int = 6 * 60 * 60

    def __post_init__(self) -> None:
        if self.max_runtime_seconds < 60:
            raise ValueError("max_runtime_seconds must be at least 60")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def campaign_runtime_limit_from_env() -> CampaignRuntimeLimit:
    raw = os.getenv("XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS")
    if raw is None:
        return CampaignRuntimeLimit()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS must be an integer") from exc
    if not 60 <= value <= 7 * 24 * 60 * 60:
        raise ValueError(
            "XBOW_CAMPAIGN_MAX_RUNTIME_SECONDS must be between 60 and 604800"
        )
    return CampaignRuntimeLimit(max_runtime_seconds=value)


@dataclass(frozen=True)
class CampaignRuntimeStatus:
    elapsed_seconds: int
    remaining_seconds: int
    exhausted: bool
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("campaign timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def runtime_status(
    created_at: str,
    limit: CampaignRuntimeLimit | None = None,
    *,
    now: datetime | None = None,
) -> CampaignRuntimeStatus:
    limits = limit or CampaignRuntimeLimit()
    started = _parse_timestamp(created_at)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    elapsed = max(0, int((current - started).total_seconds()))
    remaining = max(0, limits.max_runtime_seconds - elapsed)
    exhausted = elapsed >= limits.max_runtime_seconds
    return CampaignRuntimeStatus(
        elapsed_seconds=elapsed,
        remaining_seconds=remaining,
        exhausted=exhausted,
        reason="campaign runtime budget exhausted" if exhausted else None,
    )
