import base64
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
from app.storage import CampaignConflictError, Storage
from app.totp_auth import _totp, configured_totp_secret, consume_totp_code


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


@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_totp_replay_is_atomic_across_concurrent_consumers(monkeypatch):
    secret = base64.b32encode(uuid4().bytes).decode("ascii")
    monkeypatch.setenv("XBOW_TOTP_SECRET", secret)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_TOTP_REPLAY_BACKEND", "redis")
    monkeypatch.setenv("XBOW_TOTP_REPLAY_REDIS_URL", _redis_url())
    code = _totp(configured_totp_secret(), 1)
    barrier = threading.Barrier(8)
    results = []
    lock = threading.Lock()

    def consume():
        barrier.wait(timeout=5)
        accepted = consume_totp_code(code, now=30.0)
        with lock:
            results.append(accepted)

    threads = [threading.Thread(target=consume) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert results.count(True) == 1
    assert results.count(False) == 7


@pytest.mark.skipif(not _postgres_url(), reason="PostgreSQL integration URL unavailable")
def test_postgres_cas_stress_has_exactly_one_winner(tmp_path):
    campaign_id = f"stress-cas-{uuid4()}"
    store = PostgresStorage(
        database_url=_postgres_url(),
        artifact_root=str(tmp_path / "artifacts-stress"),
    )
    original = {
        "id": campaign_id,
        "state": "ready",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "events": [],
    }
    assert store.save_campaign(original, expected_version=0) == 1

    contenders = 16
    barrier = threading.Barrier(contenders)
    original_connect = store.connect

    @contextmanager
    def synchronized_connect():
        with original_connect() as base:
            class BarrierConnection:
                def execute(self, statement, params=()):
                    cursor = base.execute(statement, params)
                    if statement.strip().startswith("SELECT version FROM campaigns WHERE id="):
                        barrier.wait(timeout=10)
                    return cursor

            yield BarrierConnection()

    store.connect = synchronized_connect
    outcomes = []
    errors = []
    lock = threading.Lock()

    def write(index):
        document = {
            **original,
            "state": "running",
            "updated_at": f"2026-01-01T00:00:{index:02d}+00:00",
            "events": [{"type": "writer_commit", "writer": index}],
        }
        try:
            version = store.save_campaign(document, expected_version=1)
            result = ("ok", version, index)
        except CampaignConflictError:
            result = ("conflict", None, index)
        except Exception as exc:
            with lock:
                errors.append(exc)
            return
        with lock:
            outcomes.append(result)

    threads = [
        threading.Thread(target=write, args=(index,), name=f"pg-writer-{index}")
        for index in range(contenders)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    assert errors == []
    assert sum(kind == "ok" for kind, _version, _index in outcomes) == 1
    assert (
        sum(kind == "conflict" for kind, _version, _index in outcomes)
        == contenders - 1
    )
    winners = [
        (version, index)
        for kind, version, index in outcomes
        if kind == "ok"
    ]
    assert len(winners) == 1
    assert winners[0][0] == 2

    saved, version = store.get_campaign_record(campaign_id)
    assert version == 2
    assert saved["state"] == "running"
    assert saved["events"] == [
        {"type": "writer_commit", "writer": winners[0][1]}
    ]


@pytest.mark.skipif(not _redis_url(), reason="Redis integration URL unavailable")
def test_redis_claim_stress_has_no_duplicate_or_lost_jobs(monkeypatch):
    prefix = f"xbow:stress:{uuid4().hex}"
    monkeypatch.setenv("XBOW_REDIS_PREFIX", prefix)
    queue = RedisJobQueue(_redis_url())
    campaign_id = f"campaign-{uuid4()}"
    workers = 32

    created_ids = []
    for index in range(workers):
        job = queue.enqueue(
            campaign_id,
            "report",
            {"campaign_id": campaign_id, "platform": f"generic-{index}"},
        )
        created_ids.append(job["id"])

    barrier = threading.Barrier(workers)
    claimed = []
    errors = []
    lock = threading.Lock()

    def claim(index):
        try:
            barrier.wait(timeout=10)
            job = queue.claim(f"worker-{index}")
            with lock:
                claimed.append(job)
        except Exception as exc:
            with lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=claim, args=(index,), name=f"redis-worker-{index}")
        for index in range(workers)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    try:
        assert errors == []
        assert all(job is not None for job in claimed)
        claimed_ids = [job["id"] for job in claimed]
        assert len(claimed_ids) == workers
        assert len(set(claimed_ids)) == workers
        assert set(claimed_ids) == set(created_ids)
        stats = queue.stats()
        assert stats["by_status"]["queued"] == 0
        assert stats["by_status"]["running"] == workers
    finally:
        keys = list(queue.redis.scan_iter(f"{prefix}:*"))
        if keys:
            queue.redis.delete(*keys)



def test_sqlite_cas_stress_has_exactly_one_winner_and_preserves_event(tmp_path):
    store = Storage(
        str(tmp_path / "sqlite-cas.sqlite3"),
        str(tmp_path / "artifacts-sqlite-cas"),
    )
    campaign_id = f"sqlite-stress-{uuid4()}"
    original = {
        "id": campaign_id,
        "state": "ready",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "events": [],
    }
    assert store.save_campaign(original, expected_version=0) == 1

    contenders = 16
    barrier = threading.Barrier(contenders)
    outcomes = []
    errors = []
    lock = threading.Lock()

    def write(index):
        document = {
            **original,
            "state": "running",
            "updated_at": f"2026-01-01T00:00:{index:02d}+00:00",
            "events": [{"type": "writer_commit", "writer": index}],
        }
        try:
            barrier.wait(timeout=10)
            version = store.save_campaign(document, expected_version=1)
            result = ("ok", version, index)
        except CampaignConflictError:
            result = ("conflict", None, index)
        except Exception as exc:
            with lock:
                errors.append(exc)
            return
        with lock:
            outcomes.append(result)

    threads = [
        threading.Thread(target=write, args=(index,), name=f"sqlite-writer-{index}")
        for index in range(contenders)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()

    assert errors == []
    assert sum(kind == "ok" for kind, _version, _index in outcomes) == 1
    assert sum(kind == "conflict" for kind, _version, _index in outcomes) == contenders - 1
    winners = [
        (version, index)
        for kind, version, index in outcomes
        if kind == "ok"
    ]
    assert len(winners) == 1
    assert winners[0][0] == 2

    saved, version = store.get_campaign_record(campaign_id)
    assert version == 2
    assert saved["state"] == "running"
    assert saved["events"] == [
        {"type": "writer_commit", "writer": winners[0][1]}
    ]
