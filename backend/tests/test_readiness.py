from pathlib import Path

import pytest

import app.readiness as readiness


class HealthyQueue:
    def health(self):
        return {"ok": True, "database": "ok"}


class UnhealthyQueue:
    def health(self):
        return {"ok": False, "database": "corrupt"}


class ExplodingQueue:
    def __init__(self):
        raise RuntimeError("sensitive detail")


class FakeStorage:
    def __init__(self, root: Path, *, healthy: bool = True):
        self.artifact_root = root
        self.healthy = healthy

    def health(self):
        return {"ok": self.healthy, "storage": "fixture"}


def test_readiness_requires_database_and_artifact_store(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "JobQueue", HealthyQueue)
    monkeypatch.setattr(readiness, "Storage", lambda: FakeStorage(tmp_path / "artifacts"))

    result = readiness.readiness()

    assert result["ok"] is True
    assert result["queue"]["ok"] is True
    assert result["metadata"]["ok"] is True
    assert result["artifacts"]["ok"] is True


def test_readiness_fails_closed_when_database_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "JobQueue", UnhealthyQueue)
    monkeypatch.setattr(readiness, "Storage", lambda: FakeStorage(tmp_path / "artifacts"))

    result = readiness.readiness()

    assert result["ok"] is False


def test_readiness_sanitizes_queue_probe_exceptions(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "JobQueue", ExplodingQueue)
    monkeypatch.setattr(readiness, "Storage", lambda: FakeStorage(tmp_path / "artifacts"))

    result = readiness.readiness()

    assert result["ok"] is False
    assert result["queue"] == {"ok": False, "error": "RuntimeError"}


def test_readiness_sanitizes_storage_probe_exceptions(monkeypatch):
    monkeypatch.setattr(readiness, "JobQueue", HealthyQueue)

    def explode_storage():
        raise PermissionError("private path")

    monkeypatch.setattr(readiness, "Storage", explode_storage)

    result = readiness.readiness()

    assert result["ok"] is False
    assert result["metadata"] == {"ok": False, "error": "PermissionError"}
    assert result["artifacts"] == {"ok": False, "error": "StorageUnavailable"}


def test_readiness_fails_when_metadata_storage_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "JobQueue", HealthyQueue)
    monkeypatch.setattr(
        readiness,
        "Storage",
        lambda: FakeStorage(tmp_path / "artifacts", healthy=False),
    )

    result = readiness.readiness()

    assert result["ok"] is False
    assert result["queue"]["ok"] is True
    assert result["metadata"]["ok"] is False
    assert result["artifacts"]["ok"] is True


def test_artifact_store_probe_fails_for_non_directory(tmp_path):
    target = tmp_path / "artifact-file"
    target.write_text("not a directory", encoding="utf-8")

    result = readiness._artifact_store_ready(target)

    assert result["ok"] is False


def test_main_returns_normally_when_ready(monkeypatch):
    monkeypatch.setattr(readiness, "readiness", lambda: {"ok": True})
    assert readiness.main() is None


def test_main_exits_nonzero_when_not_ready(monkeypatch):
    monkeypatch.setattr(readiness, "readiness", lambda: {"ok": False})
    with pytest.raises(SystemExit) as exc:
        readiness.main()
    assert exc.value.code == 1
