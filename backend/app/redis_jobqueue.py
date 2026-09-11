from __future__ import annotations

import os


class RedisJobQueue:
    def __init__(self, url: str | None = None):
        self.url = (url or os.getenv("XBOW_REDIS_URL") or "").strip()
        if not self.url:
            raise ValueError("XBOW_REDIS_URL is required for Redis queue")
