from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from uuid import uuid4

import redis


def _planner_lock_seconds() -> int:
    raw = os.getenv("XBOW_PLANNER_LOCK_SECONDS", "30")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("XBOW_PLANNER_LOCK_SECONDS must be an integer") from exc
    if not 5 <= value <= 300:
        raise ValueError("XBOW_PLANNER_LOCK_SECONDS must be between 5 and 300")
    return value


@contextmanager
def campaign_planner_lock(queue, campaign_id: str):
    """Best-effort single-planner lease for distributed Redis deployments.

    SQLite deployments already serialize queue mutations locally and use durable
    dedupe/CAS guards, so they do not need an extra cross-process Redis lease.
    """
    client = getattr(queue, "redis", None)
    prefix = getattr(queue, "prefix", "")
    if client is None or not prefix:
        yield True
        return

    digest = hashlib.sha256(campaign_id.encode("utf-8")).hexdigest()
    key = f"{prefix}:planner-lock:{digest}"
    token = uuid4().hex
    acquired = bool(client.set(key, token, nx=True, ex=_planner_lock_seconds()))
    try:
        yield acquired
    finally:
        if acquired:
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            end
            return 0
            """
            try:
                client.eval(script, 1, key, token)
            except redis.RedisError:
                # Lease expiry is bounded; never delete a successor's lock.
                pass
