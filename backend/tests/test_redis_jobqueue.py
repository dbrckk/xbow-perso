import pytest

from app.redis_jobqueue import RedisJobQueue, _uses_generic_queue


class DummyRedis:
    def ping(self):
        return True


def test_redis_queue_rejects_missing_url(monkeypatch):
    monkeypatch.delenv("XBOW_REDIS_URL", raising=False)
    with pytest.raises(ValueError, match="XBOW_REDIS_URL is required"):
        RedisJobQueue()


def test_redis_queue_rejects_non_redis_url(monkeypatch):
    monkeypatch.setenv("XBOW_REDIS_URL", "http://localhost:6379")
    with pytest.raises(ValueError, match="must be a Redis URL"):
        RedisJobQueue()


def test_redis_queue_rejects_unsafe_prefix(monkeypatch):
    monkeypatch.setenv("XBOW_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("XBOW_REDIS_PREFIX", "bad\nprefix")
    with pytest.raises(ValueError, match="XBOW_REDIS_PREFIX is invalid"):
        RedisJobQueue()


def test_redis_queue_health_does_not_expose_configuration(monkeypatch):
    monkeypatch.setenv("XBOW_REDIS_URL", "redis://secret.example:6379/0")
    monkeypatch.setattr("app.redis_jobqueue.redis.Redis.from_url", lambda *args, **kwargs: DummyRedis())
    queue = RedisJobQueue()
    assert queue.health() == {"ok": True, "storage": "redis"}
    assert "secret.example" not in str(queue.health())


def test_pentagi_jobs_never_use_generic_redis_queue():
    assert _uses_generic_queue("pentagi_flow") is False
    assert _uses_generic_queue("pentagi_status") is False
    assert _uses_generic_queue("report") is True



class DedupeRedis(DummyRedis):
    def __init__(self, dedupe_hash, dedupe_key, job_id, job_row):
        self.dedupe_hash = dedupe_hash
        self.dedupe_key = dedupe_key
        self.job_id = job_id
        self.job_row = job_row

    def hget(self, key, field):
        if key == self.dedupe_hash and field == self.dedupe_key:
            return self.job_id
        return None

    def hgetall(self, key):
        if key.endswith(f":job:{self.job_id}"):
            return dict(self.job_row)
        return {}


def test_redis_get_by_dedupe_uses_index_without_scanning(monkeypatch):
    monkeypatch.setenv("XBOW_REDIS_URL", "redis://localhost:6379/0")
    probe = RedisJobQueue()
    dedupe_hash = probe._dedupe_key("campaign-1", "report")
    fake = DedupeRedis(
        dedupe_hash,
        "report:generic:request-1",
        "job-1",
        {
            "id": "job-1",
            "campaign_id": "campaign-1",
            "kind": "report",
            "payload": '{"campaign_id":"campaign-1","platform":"generic"}',
            "status": "queued",
            "attempts": "0",
            "max_attempts": "2",
            "created_at": "2026-09-13T10:00:00+00:00",
            "updated_at": "2026-09-13T10:00:00+00:00",
            "claimed_by": "",
            "claimed_at": "",
            "last_error": "",
            "dedupe_key": "report:generic:request-1",
        },
    )
    monkeypatch.setattr(
        "app.redis_jobqueue.redis.Redis.from_url",
        lambda *args, **kwargs: fake,
    )
    queue = RedisJobQueue()

    found = queue.get_by_dedupe(
        "campaign-1",
        "report",
        "report:generic:request-1",
    )

    assert found is not None
    assert found["id"] == "job-1"
    assert found["status"] == "queued"



class AllowedKindRedis(DummyRedis):
    def __init__(self):
        self.scores = {}

    def zrange(self, key, start, end, withscores=False):
        item = self.scores.get(key)
        if item is None:
            return []
        job_id, score = item
        return [(job_id, score)] if withscores else [job_id]


def test_redis_claim_allowed_selects_oldest_kind(monkeypatch):
    monkeypatch.setenv("XBOW_REDIS_URL", "redis://localhost:6379/0")
    fake = AllowedKindRedis()
    monkeypatch.setattr(
        "app.redis_jobqueue.redis.Redis.from_url",
        lambda *args, **kwargs: fake,
    )
    queue = RedisJobQueue()
    fake.scores[queue._queued_kind("report")] = ("report-job", 1.0)
    fake.scores[queue._queued_kind("independent_validation")] = ("validation-job", 2.0)
    monkeypatch.setattr(queue, "recover_expired_leases", lambda: 0)
    claimed_kinds = []

    def fake_claim_kind(worker_id, kind):
        claimed_kinds.append((worker_id, kind))
        return {"id": "report-job", "kind": kind}

    monkeypatch.setattr(queue, "claim_kind", fake_claim_kind)

    claimed = queue.claim_allowed(
        "worker-a",
        ("independent_validation", "report"),
    )

    assert claimed["kind"] == "report"
    assert claimed_kinds == [("worker-a", "report")]



class RecoveryPipeline:
    def __init__(self, rows):
        self.rows = rows
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def hmget(self, key, *fields):
        self.commands.append((key, fields))
        return self

    def execute(self):
        return [
            [self.rows.get(key, {}).get(field) for field in fields]
            for key, fields in self.commands
        ]


class RecoveryRedis(DummyRedis):
    def __init__(self):
        self.ids = {"job-b", "job-a"}
        self.rows = {}

    def smembers(self, _key):
        return set(self.ids)

    def pipeline(self, transaction=False):
        assert transaction is False
        return RecoveryPipeline(self.rows)


def test_redis_recovery_snapshot_is_bounded_and_payload_free(monkeypatch):
    monkeypatch.setenv("XBOW_REDIS_URL", "redis://localhost:6379/0")
    fake = RecoveryRedis()
    monkeypatch.setattr(
        "app.redis_jobqueue.redis.Redis.from_url",
        lambda *args, **kwargs: fake,
    )
    queue = RedisJobQueue()
    fake.rows[queue._job_key("job-a")] = {
        "status": "queued",
        "attempts": "0",
        "max_attempts": "2",
        "claimed_by": "",
        "claimed_at": "",
        "payload": '{"secret":"must-not-leak"}',
    }
    fake.rows[queue._job_key("job-b")] = {
        "status": "running",
        "attempts": "1",
        "max_attempts": "2",
        "claimed_by": "worker-b",
        "claimed_at": "2026-10-03T12:00:00+00:00",
        "payload": '{"secret":"must-not-leak"}',
    }

    snapshot = queue.recovery_snapshot(limit=1)

    assert snapshot == [
        {
            "id": "job-a",
            "status": "queued",
            "attempts": "0",
            "max_attempts": "2",
            "claimed_by": None,
            "claimed_at": None,
        }
    ]
    assert "payload" not in str(snapshot)
    assert "must-not-leak" not in str(snapshot)
