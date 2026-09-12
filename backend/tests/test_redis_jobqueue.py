import pytest

from app.redis_jobqueue import RedisJobQueue


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
