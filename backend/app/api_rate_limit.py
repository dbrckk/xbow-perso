from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from threading import Lock

import redis
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
    backend: str = "memory"


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
    backend = os.getenv("XBOW_API_RATE_LIMIT_BACKEND", "memory").strip().lower()
    if backend not in {"memory", "redis"}:
        raise RateLimitConfigError("XBOW_API_RATE_LIMIT_BACKEND must be memory or redis")
    return ApiRateLimitConfig(
        enabled=_strict_bool("XBOW_API_RATE_LIMIT_ENABLED", False),
        requests=_bounded_int("XBOW_API_RATE_LIMIT_REQUESTS", 120, 1, 10_000),
        window_seconds=_bounded_int("XBOW_API_RATE_LIMIT_WINDOW_SECONDS", 60, 1, 3600),
        max_keys=_bounded_int("XBOW_API_RATE_LIMIT_MAX_KEYS", 10_000, 100, 100_000),
        backend=backend,
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


class RedisFixedWindowLimiter:
    _SCRIPT = """
local window_seconds = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local member = ARGV[3]
local max_keys = tonumber(ARGV[4])

redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', window - 1)
if redis.call('EXISTS', KEYS[1]) == 0 and redis.call('ZCARD', KEYS[2]) >= max_keys then
  return {-1, window_seconds}
end

redis.call('ZADD', KEYS[2], window, member)
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], window_seconds)
end
redis.call('EXPIRE', KEYS[2], window_seconds * 2)
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""

    def __init__(self, url: str, prefix: str = "xbow:ratelimit") -> None:
        if not url.startswith(("redis://", "rediss://")):
            raise RateLimitConfigError("XBOW_API_RATE_LIMIT_REDIS_URL must be a Redis URL")
        if not prefix or len(prefix) > 100 or any(ord(ch) < 33 or ord(ch) == 127 for ch in prefix):
            raise RateLimitConfigError("XBOW_API_RATE_LIMIT_REDIS_PREFIX is invalid")
        self.prefix = prefix
        self.redis = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )

    def _key(self, client_key: str, window_seconds: int, now: float) -> str:
        window = int(now // window_seconds)
        digest = hashlib.sha256(client_key.encode("utf-8")).hexdigest()
        return f"{self.prefix}:{window}:{digest}"

    def check(self, key: str, config: ApiRateLimitConfig, *, now: float | None = None) -> tuple[bool, int]:
        timestamp = time.time() if now is None else now
        window = int(timestamp // config.window_seconds)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        redis_key = self._key(key, config.window_seconds, timestamp)
        active_key = f"{self.prefix}:active"
        try:
            count, ttl = self.redis.eval(
                self._SCRIPT,
                2,
                redis_key,
                active_key,
                config.window_seconds,
                window,
                digest,
                config.max_keys,
            )
        except redis.RedisError as exc:
            raise RuntimeError("distributed API rate limiter unavailable") from exc
        if int(count) < 0:
            raise RuntimeError("distributed API rate limiter capacity exhausted")
        retry_after = max(1, int(ttl) if int(ttl) > 0 else config.window_seconds)
        return int(count) <= config.requests, retry_after


_limiter = FixedWindowLimiter()
_distributed_limiter: RedisFixedWindowLimiter | None = None


def _active_limiter(config: ApiRateLimitConfig):
    global _distributed_limiter
    if config.backend == "memory":
        return _limiter

    url = os.getenv("XBOW_API_RATE_LIMIT_REDIS_URL", "").strip()
    if not url:
        raise RateLimitConfigError(
            "XBOW_API_RATE_LIMIT_REDIS_URL is required for redis rate limiting"
        )
    prefix = os.getenv("XBOW_API_RATE_LIMIT_REDIS_PREFIX", "xbow:ratelimit").strip()
    if _distributed_limiter is None:
        _distributed_limiter = RedisFixedWindowLimiter(url, prefix)
    return _distributed_limiter


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
        limiter = _active_limiter(config)
        allowed, retry_after = limiter.check(_client_key(request), config)
    except RateLimitConfigError:
        return JSONResponse(
            status_code=503,
            content={"detail": "API rate limiter configuration is invalid"},
        )
    except RuntimeError:
        return JSONResponse(
            status_code=503,
            content={"detail": "API rate limiter unavailable"},
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
