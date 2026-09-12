import pytest

from app.jobqueue import JobQueue
from app.queue_backend import create_queue, queue_backend_name


def test_queue_backend_defaults_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("XBOW_QUEUE_BACKEND", raising=False)
    monkeypatch.setenv("XBOW_DB_PATH", str(tmp_path / "db.sqlite3"))

    backend = create_queue()

    assert queue_backend_name() == "sqlite"
    assert isinstance(backend, JobQueue)


def test_queue_backend_accepts_sqlite_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "sqlite3")
    monkeypatch.setenv("XBOW_DB_PATH", str(tmp_path / "db.sqlite3"))

    assert queue_backend_name() == "sqlite"
    assert isinstance(create_queue(), JobQueue)


def test_queue_backend_accepts_redis(monkeypatch):
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "redis")

    assert queue_backend_name() == "redis"


def test_queue_backend_builds_redis_adapter(monkeypatch):
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "redis")
    monkeypatch.setenv("XBOW_REDIS_URL", "redis://localhost:6379/0")

    backend = create_queue()

    assert backend.__class__.__name__ == "RedisJobQueue"
    assert backend.url == "redis://localhost:6379/0"


def test_queue_backend_redis_requires_explicit_url(monkeypatch):
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "redis")
    monkeypatch.delenv("XBOW_REDIS_URL", raising=False)

    with pytest.raises(ValueError, match="XBOW_REDIS_URL is required"):
        create_queue()


def test_queue_backend_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("XBOW_QUEUE_BACKEND", "rabbitmq")

    with pytest.raises(ValueError, match="must be sqlite or redis"):
        queue_backend_name()
