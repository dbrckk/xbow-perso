import os
import threading
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from app.postgres_storage import PostgresStorage, _PostgresCompatConnection
from app.redis_jobqueue import RedisJobQueue
from app.planner_lock import campaign_planner_lock
from app.storage import CampaignConflictError


def _postgres_url():
    return os.getenv("XBOW_TEST_POSTGRES_URL", "").strip()


def _redis_url():
    return os.getenv("XBOW_REDIS_URL", "").strip()


@pytest.mark.skipif(not _postgres_url(), reason="PostgreSQL integration URL unavailable")
def test_postgres_campaign_cas_detects_concurrent_lost_update(tmp_path):
    campaign_id = f"cas-{uuid4()}"
    store = PostgresStorage(
        database_url=_postgres_url(),
        artifact_root=str(tmp_path / "artifacts"),
    )
    original = {
        "id": campaign_id,
        "state": "ready",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    assert store.save_campaign(original, expected_version=0) == 1

    barrier = threading.Barrier(2)

    @contextmanager
    def synchronized_connect():
        connection = psycopg.connect(
            store.database_url,
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=10,
        )

        class BarrierConnection(_PostgresCompatConnection):
            def execute(self, statement, params=()):
                cursor = super().execute(statement, params)
                if statement.strip().startswith("SELECT version FROM campaigns WHERE id="):
                    barrier.wait(timeout=5)
                return cursor

        try:
            yield BarrierConnection(connection)
        finally:
            connection.close()

    store.connect = synchronized_connect
    outcomes = []
    lock = threading.Lock()

    def write(state):
        document = {
            **original,
            "state": state,
            "updated_at": f"2026-01-01T00:00:0{1 if state == 'running' else 2}+00:00",
        }
        try:
            version = store.save_campaign(document, expected_version=1)
            result = ("ok", version)
        except CampaignConflictError:
            result = ("conflict", None)
        with lock:
            outcomes.append(result)

    threads = [
        threading.Thread(target=write, args=("running",)),
        threading.Thread(target=write, args=("completed",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert sorted(kind for kind, _version in outcomes) == ["conflict", "ok"]
    assert [version for kind, version in outcomes if kind == "ok"] == [2]
    saved, version = store.get_campaign_record(campaign_id)
    assert version == 2
    assert saved["state"] in {"running", "completed"}


@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_dedupe_is_atomic_under_concurrent_enqueue(monkeypatch):
    prefix = f"xbow:test:{uuid4().hex}"
    monkeypatch.setenv("XBOW_REDIS_PREFIX", prefix)
    queue = RedisJobQueue(_redis_url())
    campaign_id = f"campaign-{uuid4()}"
    barrier = threading.Barrier(8)
    job_ids = []
    errors = []
    lock = threading.Lock()

    def enqueue():
        try:
            barrier.wait(timeout=5)
            job = queue.enqueue(
                campaign_id,
                "report",
                {"campaign_id": campaign_id, "platform": "generic"},
                dedupe_key="same-report",
            )
            with lock:
                job_ids.append(job["id"])
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=enqueue) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    try:
        assert errors == []
        assert len(job_ids) == 8
        assert len(set(job_ids)) == 1
        assert queue.stats()["total"] == 1
    finally:
        keys = list(queue.redis.scan_iter(f"{prefix}:*"))
        if keys:
            queue.redis.delete(*keys)


@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_campaign_planner_lock_has_single_concurrent_owner(monkeypatch):
    prefix = f"xbow:test:{uuid4().hex}"
    monkeypatch.setenv("XBOW_REDIS_PREFIX", prefix)
    queue = RedisJobQueue(_redis_url())
    campaign_id = f"campaign-{uuid4()}"
    barrier = threading.Barrier(8)
    release = threading.Event()
    owners = []
    contenders = []
    lock = threading.Lock()

    def compete():
        barrier.wait(timeout=5)
        with campaign_planner_lock(queue, campaign_id) as acquired:
            with lock:
                (owners if acquired else contenders).append(threading.current_thread().name)
            if acquired:
                release.wait(timeout=5)

    threads = [threading.Thread(target=compete, name=f"planner-{i}") for i in range(8)]
    for thread in threads:
        thread.start()

    for _ in range(50):
        with lock:
            if len(owners) == 1 and len(contenders) == 7:
                break
        threading.Event().wait(0.02)
    release.set()

    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    try:
        assert len(owners) == 1
        assert len(contenders) == 7
        with campaign_planner_lock(queue, campaign_id) as acquired_after_release:
            assert acquired_after_release is True
    finally:
        keys = list(queue.redis.scan_iter(f"{prefix}:*"))
        if keys:
            queue.redis.delete(*keys)


def test_planner_lock_configuration_fails_closed(monkeypatch, tmp_path):
    from app.jobqueue import JobQueue

    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    monkeypatch.setenv("XBOW_PLANNER_LOCK_SECONDS", "not-an-int")

    # Local SQLite mode does not depend on the distributed lease configuration.
    with campaign_planner_lock(queue, "campaign-local") as acquired:
        assert acquired is True


@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_planner_lock_rejects_invalid_lease(monkeypatch):
    prefix = f"xbow:test:{uuid4().hex}"
    monkeypatch.setenv("XBOW_REDIS_PREFIX", prefix)
    monkeypatch.setenv("XBOW_PLANNER_LOCK_SECONDS", "301")
    queue = RedisJobQueue(_redis_url())

    with pytest.raises(ValueError, match="XBOW_PLANNER_LOCK_SECONDS"):
        with campaign_planner_lock(queue, "campaign-invalid"):
            pass
