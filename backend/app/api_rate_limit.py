from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class RateLimitConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ApiRateLimitConfig:
    enabled: bool
    requests: int
    window_seconds: int
    max_keys: int


def _strict_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RateLimitConfigError(f"{name} must be a boolean")


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RateLimitConfigError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise RateLimitConfigError(f"{name} must be between {low} and {high}")
    return value


def load_api_rate_limit_config() -> ApiRateLimitConfig:
    return ApiRateLimitConfig(
        enabled=_strict_bool("XBOW_API_RATE_LIMIT_ENABLED", False),
        requests=_bounded_int("XBOW_API_RATE_LIMIT_REQUESTS", 120, 1, 10_000),
        window_seconds=_bounded_int("XBOW_API_RATE_LIMIT_WINDOW_SECONDS", 60, 1, 3600),
        max_keys=_bounded_int("XBOW_API_RATE_LIMIT_MAX_KEYS", 10_000, 100, 100_000),
    )


class FixedWindowLimiter:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    def _prune(self, current_window: int, max_keys: int) -> None:
        stale = [key for key, (window, _count) in self._entries.items() if window != current_window]
        for key in stale:
            self._entries.pop(key, None)
        if len(self._entries) >= max_keys:
            # Fail closed at capacity instead of evicting an active key and resetting its quota.
            raise RuntimeError("API rate limiter capacity exhausted")

    def check(self, key: str, config: ApiRateLimitConfig, *, now: float | None = None) -> tuple[bool, int]:
        timestamp = time.time() if now is None else now
        window = int(timestamp // config.window_seconds)
        retry_after = max(1, config.window_seconds - int(timestamp % config.window_seconds))

        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[0] != window:
                self._prune(window, config.max_keys)
                self._entries[key] = (window, 1)
                return True, retry_after

            count = entry[1]
            if count >= config.requests:
                return False, retry_after
            self._entries[key] = (window, count + 1)
            return True, retry_after


_limiter = FixedWindowLimiter()


def _client_key(request: Request) -> str:
    # Deliberately ignore X-Forwarded-For/X-Real-IP unless a trusted proxy layer rewrites
    # request.client itself. This avoids spoofable-header bypasses.
    client = request.client
    host = client.host if client and client.host else "unknown"
    return str(host)


async def api_rate_limit_middleware(request: Request, call_next):
    if not (request.url.path.startswith("/api/") or request.url.path == "/api"):
        return await call_next(request)

    try:
        config = load_api_rate_limit_config()
    except RateLimitConfigError:
        return JSONResponse(
            status_code=503,
            content={"detail": "API rate limiter configuration is invalid"},
        )

    if not config.enabled:
        return await call_next(request)

    try:
        allowed, retry_after = _limiter.check(_client_key(request), config)
    except RuntimeError:
        return JSONResponse(
            status_code=503,
            content={"detail": "API rate limiter capacity exhausted"},
        )

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "API rate limit exceeded"},
            headers={"Retry-After": str(retry_after)},
        )
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(config.requests)
    return response
