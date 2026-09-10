from pathlib import Path

import app.readiness as readiness


class HealthyQueue:
    def health(self):
        return {"ok": True, "database": "ok"}


class UnhealthyQueue:
    def health(self):
        return {"ok": False, "database": "corrupt"}


class FakeStorage:
    def __init__(self, root: Path):
        self.artifact_root = root


def test_readiness_requires_database_and_artifact_store(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "JobQueue", HealthyQueue)
    monkeypatch.setattr(readiness, "Storage", lambda: FakeStorage(tmp_path / "artifacts"))

    result = readiness.readiness()

    assert result["ok"] is True
    assert result["database"]["ok"] is True
    assert result["artifacts"]["ok"] is True


def test_readiness_fails_closed_when_database_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(readiness, "JobQueue", UnhealthyQueue)
    monkeypatch.setattr(readiness, "Storage", lambda: FakeStorage(tmp_path / "artifacts"))

    result = readiness.readiness()

    assert result["ok"] is False


def test_artifact_store_probe_fails_for_non_directory(tmp_path):
    target = tmp_path / "artifact-file"
    target.write_text("not a directory", encoding="utf-8")

    result = readiness._artifact_store_ready(target)

    assert result["ok"] is False
