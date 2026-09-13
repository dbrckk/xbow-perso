from __future__ import annotations

import os
from uuid import uuid4

import pytest
import redis

from app.redis_jobqueue import RedisJobQueue


@pytest.fixture
def redis_queue(monkeypatch):
    url = os.getenv("XBOW_REDIS_URL")
    if not url:
        pytest.skip("XBOW_REDIS_URL is not configured")

    prefix = f"xbow:test:{uuid4().hex}"
    monkeypatch.setenv("XBOW_REDIS_PREFIX", prefix)
    queue = RedisJobQueue(url)
    try:
        queue.redis.ping()
    except redis.RedisError:
        pytest.skip("Redis integration service is unavailable")

    yield queue

    keys = list(queue.redis.scan_iter(match=f"{prefix}:*"))
    if keys:
        queue.redis.delete(*keys)


def test_redis_dedupe_survives_adapter_restart(redis_queue):
    payload = {
        "campaign_id": "redis-restart",
        "platform": "generic",
    }
    first = redis_queue.enqueue(
        "redis-restart",
        "report",
        payload,
        max_attempts=2,
        dedupe_key="report:generic:restart",
    )

    restarted = RedisJobQueue(redis_queue.url)
    recovered = restarted.get_by_dedupe(
        "redis-restart",
        "report",
        "report:generic:restart",
    )
    duplicate = restarted.enqueue(
        "redis-restart",
        "report",
        payload,
        max_attempts=2,
        dedupe_key="report:generic:restart",
    )

    assert recovered is not None
    assert recovered["id"] == first["id"]
    assert duplicate["id"] == first["id"]
    assert restarted.stats()["total"] == 1

    with pytest.raises(ValueError, match="different job payload"):
        restarted.enqueue(
            "redis-restart",
            "report",
            {
                "campaign_id": "redis-restart",
                "platform": "hackerone",
            },
            max_attempts=2,
            dedupe_key="report:generic:restart",
        )


def test_redis_expired_lease_recovery_is_restart_safe(redis_queue, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    job = redis_queue.enqueue(
        "redis-lease",
        "report",
        {"campaign_id": "redis-lease", "platform": "generic"},
        max_attempts=2,
        dedupe_key="report:generic:lease",
    )
    claimed = redis_queue.claim("worker-before-restart")
    assert claimed is not None
    assert claimed["id"] == job["id"]
    assert claimed["attempts"] == 1

    redis_queue.redis.zadd(redis_queue._running, {job["id"]: 0})
    redis_queue.redis.hset(
        redis_queue._job_key(job["id"]),
        mapping={"claimed_at": "2000-01-01T00:00:00+00:00"},
    )

    restarted = RedisJobQueue(redis_queue.url)
    assert restarted.recover_expired_leases() == 1

    recovered = restarted.get(job["id"])
    assert recovered is not None
    assert recovered["status"] == "queued"
    assert recovered["claimed_by"] is None

    reclaimed = restarted.claim("worker-after-restart")
    assert reclaimed is not None
    assert reclaimed["id"] == job["id"]
    assert reclaimed["attempts"] == 2
    assert reclaimed["claimed_by"] == "worker-after-restart"


def test_redis_dedicated_job_stays_isolated_after_lease_recovery(
    redis_queue,
    monkeypatch,
):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    job = redis_queue.enqueue(
        "redis-pentagi",
        "pentagi_flow",
        {"request": {"query": "mutation { noop }"}},
        max_attempts=2,
        dedupe_key="pentagi:redis-recovery",
    )
    claimed = redis_queue.claim_kind("pentagi-worker-before", "pentagi_flow")
    assert claimed is not None
    assert claimed["id"] == job["id"]

    redis_queue.redis.zadd(redis_queue._running, {job["id"]: 0})
    redis_queue.redis.hset(
        redis_queue._job_key(job["id"]),
        mapping={"claimed_at": "2000-01-01T00:00:00+00:00"},
    )

    restarted = RedisJobQueue(redis_queue.url)
    assert restarted.recover_expired_leases() == 1
    assert restarted.claim("generic-worker") is None

    reclaimed = restarted.claim_kind("pentagi-worker-after", "pentagi_flow")
    assert reclaimed is not None
    assert reclaimed["id"] == job["id"]
    assert reclaimed["kind"] == "pentagi_flow"
    assert reclaimed["attempts"] == 2



def test_redis_stats_expose_running_lease_without_worker_identity(redis_queue):
    job = redis_queue.enqueue(
        "redis-running-metrics",
        "report",
        {"campaign_id": "redis-running-metrics", "platform": "generic"},
        dedupe_key="report:generic:running-metrics",
    )
    claimed = redis_queue.claim("redis-worker-secret-name")
    assert claimed is not None and claimed["id"] == job["id"]

    redis_queue.redis.hset(
        redis_queue._job_key(job["id"]),
        mapping={"claimed_at": "2026-09-13T10:00:00+00:00"},
    )

    stats = redis_queue.stats()

    assert stats["oldest_running_claimed_at"] == "2026-09-13T10:00:00+00:00"
    assert "redis-worker-secret-name" not in str(stats)



def test_redis_heartbeat_renews_only_current_owner(redis_queue):
    job = redis_queue.enqueue(
        "redis-heartbeat",
        "report",
        {"campaign_id": "redis-heartbeat", "platform": "generic"},
        dedupe_key="report:generic:heartbeat",
    )
    claimed = redis_queue.claim("heartbeat-owner")
    assert claimed is not None and claimed["id"] == job["id"]

    key = redis_queue._job_key(job["id"])
    redis_queue.redis.hset(
        key,
        mapping={"claimed_at": "2000-01-01T00:00:00+00:00"},
    )
    redis_queue.redis.zadd(redis_queue._running, {job["id"]: 1})

    assert redis_queue.heartbeat(job["id"], "wrong-worker") is False
    unchanged = redis_queue.get(job["id"])
    assert unchanged is not None
    assert unchanged["claimed_at"] == "2000-01-01T00:00:00+00:00"
    assert redis_queue.redis.zscore(redis_queue._running, job["id"]) == 1

    assert redis_queue.heartbeat(job["id"], "heartbeat-owner") is True
    renewed = redis_queue.get(job["id"])
    assert renewed is not None
    assert renewed["claimed_at"] != "2000-01-01T00:00:00+00:00"
    assert redis_queue.redis.zscore(redis_queue._running, job["id"]) > 1


def test_redis_stale_worker_cannot_finish_reclaimed_job(redis_queue, monkeypatch):
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    job = redis_queue.enqueue(
        "redis-ownership",
        "report",
        {"campaign_id": "redis-ownership", "platform": "generic"},
        max_attempts=2,
        dedupe_key="report:generic:ownership",
    )
    first = redis_queue.claim("worker-before-reclaim")
    assert first is not None and first["id"] == job["id"]

    redis_queue.redis.zadd(redis_queue._running, {job["id"]: 0})
    redis_queue.redis.hset(
        redis_queue._job_key(job["id"]),
        mapping={"claimed_at": "2000-01-01T00:00:00+00:00"},
    )

    second = redis_queue.claim("worker-after-reclaim")
    assert second is not None
    assert second["id"] == job["id"]
    assert second["attempts"] == 2
    assert second["claimed_by"] == "worker-after-reclaim"

    assert redis_queue.finish(
        job["id"],
        "worker-before-reclaim",
        True,
    ) is None

    current = redis_queue.get(job["id"])
    assert current is not None
    assert current["status"] == "running"
    assert current["claimed_by"] == "worker-after-reclaim"

    completed = redis_queue.finish(
        job["id"],
        "worker-after-reclaim",
        True,
    )
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["claimed_by"] is None
