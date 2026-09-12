import asyncio

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

import app.api_rate_limit as rate_limit
from app.api_rate_limit import (
    ApiRateLimitConfig,
    FixedWindowLimiter,
    RedisFixedWindowLimiter,
    RateLimitConfigError,
    _client_key,
    api_rate_limit_middleware,
    load_api_rate_limit_config,
)


def _request(path="/api/test", headers=()):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": list(headers),
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
            "http_version": "1.1",
        }
    )


async def _ok(_request):
    return JSONResponse({"ok": True})


def test_rate_limit_defaults_disabled(monkeypatch):
    monkeypatch.delenv("XBOW_API_RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.delenv("XBOW_API_RATE_LIMIT_REQUESTS", raising=False)
    monkeypatch.delenv("XBOW_API_RATE_LIMIT_WINDOW_SECONDS", raising=False)
    monkeypatch.delenv("XBOW_API_RATE_LIMIT_MAX_KEYS", raising=False)

    config = load_api_rate_limit_config()

    assert config.enabled is False
    assert config.requests == 120
    assert config.window_seconds == 60


def test_rate_limit_rejects_invalid_configuration(monkeypatch):
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_REQUESTS", "0")

    with pytest.raises(RateLimitConfigError, match="between 1 and 10000"):
        load_api_rate_limit_config()


def test_fixed_window_limiter_enforces_quota_and_retry_after():
    limiter = FixedWindowLimiter()
    config = ApiRateLimitConfig(enabled=True, requests=2, window_seconds=60, max_keys=100)

    assert limiter.check("client-a", config, now=120.0)[0] is True
    assert limiter.check("client-a", config, now=121.0)[0] is True
    allowed, retry_after = limiter.check("client-a", config, now=122.0)

    assert allowed is False
    assert 1 <= retry_after <= 60
    assert limiter.check("client-a", config, now=180.0)[0] is True


def test_fixed_window_limiter_fails_closed_at_key_capacity():
    limiter = FixedWindowLimiter()
    config = ApiRateLimitConfig(enabled=True, requests=10, window_seconds=60, max_keys=2)

    assert limiter.check("a", config, now=1.0)[0] is True
    assert limiter.check("b", config, now=1.0)[0] is True
    with pytest.raises(RuntimeError, match="capacity exhausted"):
        limiter.check("c", config, now=1.0)


def test_client_key_ignores_forwarded_headers():
    request = _request(headers=[(b"x-forwarded-for", b"203.0.113.99")])

    assert _client_key(request) == "127.0.0.1"


def test_rate_limit_middleware_returns_429(monkeypatch):
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_MAX_KEYS", "100")
    monkeypatch.setattr(rate_limit, "_limiter", FixedWindowLimiter())

    first = asyncio.run(api_rate_limit_middleware(_request(), _ok))
    second = asyncio.run(api_rate_limit_middleware(_request(), _ok))

    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "1"
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1


def test_non_api_paths_are_not_rate_limited(monkeypatch):
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setattr(rate_limit, "_limiter", FixedWindowLimiter())

    first = asyncio.run(api_rate_limit_middleware(_request("/healthz"), _ok))
    second = asyncio.run(api_rate_limit_middleware(_request("/healthz"), _ok))

    assert first.status_code == 200
    assert second.status_code == 200


class _FakeRedis:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def eval(self, *args):
        self.calls.append(args)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_distributed_limiter_enforces_shared_counter(monkeypatch):
    limiter = object.__new__(RedisFixedWindowLimiter)
    limiter.prefix = "xbow:ratelimit"
    limiter.redis = _FakeRedis([(1, 60), (2, 59), (3, 58)])
    config = ApiRateLimitConfig(
        enabled=True,
        requests=2,
        window_seconds=60,
        max_keys=100,
        backend="redis",
    )

    assert limiter.check("client-a", config, now=120.0)[0] is True
    assert limiter.check("client-a", config, now=121.0)[0] is True
    allowed, retry_after = limiter.check("client-a", config, now=122.0)

    assert allowed is False
    assert retry_after == 58
    assert limiter.redis.calls[0][1] == 2


def test_distributed_limiter_fails_closed_on_capacity():
    limiter = object.__new__(RedisFixedWindowLimiter)
    limiter.prefix = "xbow:ratelimit"
    limiter.redis = _FakeRedis([(-1, 60)])
    config = ApiRateLimitConfig(
        enabled=True,
        requests=10,
        window_seconds=60,
        max_keys=100,
        backend="redis",
    )

    with pytest.raises(RuntimeError, match="capacity exhausted"):
        limiter.check("client-a", config, now=120.0)


def test_distributed_limiter_fails_closed_on_redis_error():
    import redis

    limiter = object.__new__(RedisFixedWindowLimiter)
    limiter.prefix = "xbow:ratelimit"
    limiter.redis = _FakeRedis([redis.RedisError("down")])
    config = ApiRateLimitConfig(
        enabled=True,
        requests=10,
        window_seconds=60,
        max_keys=100,
        backend="redis",
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        limiter.check("client-a", config, now=120.0)


def test_rate_limit_config_supports_redis_backend(monkeypatch):
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_BACKEND", "redis")

    config = load_api_rate_limit_config()

    assert config.backend == "redis"


def test_rate_limit_config_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("XBOW_API_RATE_LIMIT_BACKEND", "sqlite")

    with pytest.raises(RateLimitConfigError, match="memory or redis"):
        load_api_rate_limit_config()
