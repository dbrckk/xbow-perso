import pytest

from app.storage import Storage
from app.storage_backend import create_storage, storage_backend_name


def test_storage_backend_defaults_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("XBOW_STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("XBOW_DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", str(tmp_path / "artifacts"))

    backend = create_storage()

    assert storage_backend_name() == "sqlite"
    assert isinstance(backend, Storage)


def test_storage_backend_accepts_sqlite_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_STORAGE_BACKEND", "sqlite3")
    monkeypatch.setenv("XBOW_DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", str(tmp_path / "artifacts"))

    assert storage_backend_name() == "sqlite"
    assert isinstance(create_storage(), Storage)


def test_storage_backend_normalizes_postgres_alias(monkeypatch):
    monkeypatch.setenv("XBOW_STORAGE_BACKEND", "postgres")

    assert storage_backend_name() == "postgresql"


def test_storage_backend_fails_closed_for_uninstalled_postgres(monkeypatch):
    monkeypatch.setenv("XBOW_STORAGE_BACKEND", "postgresql")

    with pytest.raises(RuntimeError, match="PostgreSQL storage backend is selected but not installed"):
        create_storage()


def test_storage_backend_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("XBOW_STORAGE_BACKEND", "mongo")

    with pytest.raises(ValueError, match="must be sqlite or postgresql"):
        storage_backend_name()
