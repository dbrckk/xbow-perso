from __future__ import annotations

import os

import redis


class RedisJobQueue:
    def __init__(self, url: str | None = None):
        self.url = (url or os.getenv("XBOW_REDIS_URL") or "").strip()
        if not self.url:
            raise ValueError("XBOW_REDIS_URL is required for Redis queue")
        if not self.url.startswith(("redis://", "rediss://")):
            raise ValueError("XBOW_REDIS_URL must be a Redis URL")
        self.redis = redis.Redis.from_url(
            self.url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
