import pytest

from app.postgres_storage import PostgresStorage, _PostgresCompatConnection


def test_postgres_sql_compat_translates_placeholders():
    assert _PostgresCompatConnection._sql(
        "SELECT * FROM campaigns WHERE id=? AND state=?"
    ) == "SELECT * FROM campaigns WHERE id=%s AND state=%s"


def test_postgres_sql_compat_translates_begin_immediate():
    assert _PostgresCompatConnection._sql("BEGIN IMMEDIATE") == "BEGIN"
    assert _PostgresCompatConnection._sql("  BEGIN IMMEDIATE  ") == "BEGIN"


def test_postgres_storage_requires_database_url(monkeypatch):
    monkeypatch.delenv("XBOW_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="XBOW_DATABASE_URL is required"):
        PostgresStorage()


def test_postgres_storage_rejects_non_postgres_url(monkeypatch):
    monkeypatch.setenv("XBOW_DATABASE_URL", "sqlite:///tmp/db.sqlite3")

    with pytest.raises(ValueError, match="must be a PostgreSQL URL"):
        PostgresStorage()


def test_postgres_storage_rejects_url_without_host(monkeypatch):
    monkeypatch.setenv("XBOW_DATABASE_URL", "postgresql:///xbow")

    with pytest.raises(ValueError, match="must be a PostgreSQL URL"):
        PostgresStorage()
