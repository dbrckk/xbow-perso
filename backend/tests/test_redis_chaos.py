from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest

from app.redis_jobqueue import RedisJobQueue


@pytest.fixture
def redis_queue(monkeypatch):
    url = os.getenv("XBOW_REDIS_URL")
    if not url:
        pytest.skip("XBOW_REDIS_URL is not configured")

    prefix = f"xbow:test:chaos:{uuid4().hex}"
    monkeypatch.setenv("XBOW_REDIS_PREFIX", prefix)
    queue = RedisJobQueue(url)
    if not queue.health().get("ok"):
        pytest.skip("Redis is unavailable")

    try:
        yield queue
    finally:
        keys = list(queue.redis.scan_iter(match=f"{prefix}:*"))
        if keys:
            queue.redis.delete(*keys)


def test_redis_restart_preserves_dedupe_identity(redis_queue):
    first = redis_queue
    created = first.enqueue(
        "campaign-redis-restart",
        "report",
        {
            "campaign_id": "campaign-redis-restart",
            "platform": "generic",
        },
        dedupe_key="report:generic:restart-1",
    )

    restarted = RedisJobQueue(first.url)
    recovered = restarted.get_by_dedupe(
        "campaign-redis-restart",
        "report",
        "report:generic:restart-1",
    )

    assert recovered is not None
    assert recovered["id"] == created["id"]
    assert recovered["status"] == "queued"
    assert restarted.stats()["total"] == 1


def test_redis_restart_preserves_terminal_status(redis_queue):
    first = redis_queue
    created = first.enqueue(
        "campaign-redis-terminal",
        "report",
        {
            "campaign_id": "campaign-redis-terminal",
            "platform": "generic",
        },
        max_attempts=1,
        dedupe_key="report:generic:terminal-1",
    )
    claimed = first.claim("worker-before-restart")
    assert claimed is not None
    assert claimed["id"] == created["id"]

    failed = first.finish(
        created["id"],
        "worker-before-restart",
        False,
        "terminal fixture",
    )
    assert failed is not None
    assert failed["status"] == "failed"

    restarted = RedisJobQueue(first.url)
    recovered = restarted.get_by_dedupe(
        "campaign-redis-terminal",
        "report",
        "report:generic:terminal-1",
    )

    assert recovered is not None
    assert recovered["id"] == created["id"]
    assert recovered["status"] == "failed"
    assert restarted.claim("worker-after-restart") is None


def test_redis_restart_recovers_expired_lease(redis_queue, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    first = redis_queue
    created = first.enqueue(
        "campaign-redis-lease",
        "report",
        {
            "campaign_id": "campaign-redis-lease",
            "platform": "generic",
        },
        max_attempts=2,
        dedupe_key="report:generic:lease-1",
    )
    claimed = first.claim("dead-worker")
    assert claimed is not None
    assert claimed["id"] == created["id"]

    old_score = time.time() - 3600
    first.redis.zadd(first._running, {created["id"]: old_score})
    first.redis.hset(
        first._job_key(created["id"]),
        mapping={"claimed_at": "2000-01-01T00:00:00+00:00"},
    )

    restarted = RedisJobQueue(first.url)
    assert restarted.recover_expired_leases() == 1

    recovered = restarted.get(created["id"])
    assert recovered is not None
    assert recovered["status"] == "queued"
    assert recovered["claimed_by"] is None
    assert recovered["claimed_at"] is None

    replacement = restarted.claim("replacement-worker")
    assert replacement is not None
    assert replacement["id"] == created["id"]
    assert replacement["attempts"] == 2


def test_redis_restart_keeps_pentagi_out_of_generic_workers(redis_queue):
    first = redis_queue
    created = first.enqueue(
        "campaign-redis-pentagi",
        "pentagi_flow",
        {"request": {"query": "mutation { noop }"}},
        max_attempts=1,
        dedupe_key="pentagi:restart-1",
    )

    restarted = RedisJobQueue(first.url)

    assert restarted.claim("generic-worker") is None

    claimed = restarted.claim_kind("pentagi-worker", "pentagi_flow")
    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["kind"] == "pentagi_flow"
    assert claimed["attempts"] == 1


def test_redis_dedupe_survives_new_client_instances(redis_queue):
    first = redis_queue
    payload = {
        "campaign_id": "campaign-redis-dedupe",
        "platform": "generic",
    }
    created = first.enqueue(
        "campaign-redis-dedupe",
        "report",
        payload,
        dedupe_key="report:generic:stable",
    )

    second = RedisJobQueue(first.url)
    third = RedisJobQueue(first.url)

    same_second = second.enqueue(
        "campaign-redis-dedupe",
        "report",
        payload,
        dedupe_key="report:generic:stable",
    )
    same_third = third.enqueue(
        "campaign-redis-dedupe",
        "report",
        payload,
        dedupe_key="report:generic:stable",
    )

    assert created["id"] == same_second["id"] == same_third["id"]
    assert third.stats()["total"] == 1
