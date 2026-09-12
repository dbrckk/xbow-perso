from __future__ import annotations

from uuid import uuid4

import pytest

from app.redis_jobqueue import RedisJobQueue


@pytest.fixture
def redis_queue(monkeypatch):
    url = "redis://localhost:6379/15"
    prefix = f"xbow:test:{uuid4().hex}"
    monkeypatch.setenv("XBOW_REDIS_URL", url)
    monkeypatch.setenv("XBOW_REDIS_PREFIX", prefix)
    queue = RedisJobQueue()
    try:
        assert queue.redis.ping() is True
        yield queue
    finally:
        keys = list(queue.redis.scan_iter(match=f"{prefix}:*"))
        if keys:
            queue.redis.delete(*keys)


def test_redis_queue_roundtrip(redis_queue):
    created = redis_queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1"},
        dedupe_key="report:v1",
    )

    claimed = redis_queue.claim("worker-a")
    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["claimed_by"] == "worker-a"
    assert claimed["attempts"] == 1

    completed = redis_queue.finish(created["id"], "worker-a", True)
    assert completed is not None
    assert completed["status"] == "completed"
    assert redis_queue.stats()["by_status"]["completed"] == 1


def test_redis_queue_dedupe_and_payload_mismatch_fail_closed(redis_queue):
    payload = {"finding_id": "f1"}
    first = redis_queue.enqueue(
        "campaign-1",
        "independent_validation",
        payload,
        dedupe_key="validation:f1",
    )
    second = redis_queue.enqueue(
        "campaign-1",
        "independent_validation",
        payload,
        dedupe_key="validation:f1",
    )

    assert second["id"] == first["id"]

    with pytest.raises(ValueError, match="different job payload"):
        redis_queue.enqueue(
            "campaign-1",
            "independent_validation",
            {"finding_id": "f2"},
            dedupe_key="validation:f1",
        )


def test_redis_queue_enforces_lease_ownership(redis_queue):
    job = redis_queue.enqueue("campaign-1", "report", {}, max_attempts=2)
    claimed = redis_queue.claim("worker-a")
    assert claimed is not None
    assert claimed["id"] == job["id"]

    assert redis_queue.heartbeat(job["id"], "worker-b") is False
    assert redis_queue.finish(job["id"], "worker-b", True) is None

    current = redis_queue.get(job["id"])
    assert current is not None
    assert current["status"] == "running"
    assert current["claimed_by"] == "worker-a"


def test_redis_queue_retry_budget(redis_queue):
    job = redis_queue.enqueue("campaign-1", "report", {}, max_attempts=2)

    first = redis_queue.claim("worker-a")
    assert first is not None
    requeued = redis_queue.finish(job["id"], "worker-a", False, "transient")
    assert requeued is not None
    assert requeued["status"] == "queued"

    second = redis_queue.claim("worker-b")
    assert second is not None
    assert second["attempts"] == 2

    failed = redis_queue.finish(job["id"], "worker-b", False, "persistent")
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["last_error"] == "persistent"
