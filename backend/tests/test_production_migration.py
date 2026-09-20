from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import app.production_migration as production_migration_module

from app.jobqueue import JobQueue
from app.production_migration import (
    ProductionMigrationError,
    _verify_artifacts,
    plan_migration,
)
from app.storage import Storage


class _FakePostgres:
    def health(self):
        return {"ok": True, "storage": "postgresql"}


class _FakeQueue:
    def health(self):
        return {"ok": True, "storage": "redis"}

    def stats(self):
        return {
            "total": 0,
            "by_status": {
                "queued": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "cancelled": 0,
            },
        }


def _campaign(campaign_id: str = "campaign-1") -> dict:
    return {
        "id": campaign_id,
        "state": "draft",
        "created_at": "2026-09-20T00:00:00+00:00",
        "updated_at": "2026-09-20T00:00:00+00:00",
        "target": {
            "name": "Example",
            "primary_url": "https://app.example.com/",
            "rules": {
                "authorization_reference": "https://example.com/policy",
                "allowed_targets": ["app.example.com"],
                "denied_targets": [],
            },
        },
        "findings": [],
        "events": [],
    }


def _configure_source(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "xbow.sqlite3"
    artifact_root = tmp_path / "artifacts"
    store = Storage(db_path=str(db_path), artifact_root=str(artifact_root))
    store.save_campaign(_campaign(), expected_version=0)
    monkeypatch.setenv("XBOW_MIGRATION_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.setenv("XBOW_DATABASE_URL", "postgresql://xbow:test@postgres/xbow")
    monkeypatch.setenv("XBOW_REDIS_URL", "redis://redis:6379/0")
    return db_path, artifact_root


def test_plan_reports_source_counts_without_exposing_payloads(monkeypatch, tmp_path):
    db_path, _artifact_root = _configure_source(monkeypatch, tmp_path)
    queue = JobQueue(path=str(db_path))
    queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1", "platform": "generic"},
        dedupe_key="report:test",
    )

    monkeypatch.setattr(
        "app.production_migration._initialize_targets",
        lambda: (_FakePostgres(), _FakeQueue()),
    )
    monkeypatch.setattr(
        "app.production_migration._postgres_counts",
        lambda _url: {
            "campaigns": 0,
            "artifacts": 0,
            "observations": 0,
            "hypothesis_snapshots": 0,
            "advisory_focus_snapshots": 0,
            "pentagi_flow_bindings": 0,
        },
    )
    monkeypatch.setattr(
        "app.production_migration._target_redis_count",
        lambda _queue: 0,
    )

    result = plan_migration()

    assert result["ok"] is True
    assert result["source"]["counts"]["campaigns"] == 1
    assert result["source"]["counts"]["jobs"] == 1
    assert result["source"]["queue_by_status"]["queued"] == 1
    assert result["copies_queue_history"] is True
    assert result["contains_secrets"] is False
    assert result["contains_payloads"] is False
    assert "platform" not in str(result)


def test_plan_blocks_running_jobs(monkeypatch, tmp_path):
    db_path, _artifact_root = _configure_source(monkeypatch, tmp_path)
    queue = JobQueue(path=str(db_path))
    queued = queue.enqueue(
        "campaign-1",
        "report",
        {"campaign_id": "campaign-1", "platform": "generic"},
    )
    claimed = queue.claim("worker-1")
    assert claimed is not None
    assert claimed["id"] == queued["id"]

    monkeypatch.setattr(
        "app.production_migration._initialize_targets",
        lambda: (_FakePostgres(), _FakeQueue()),
    )
    monkeypatch.setattr(
        "app.production_migration._postgres_counts",
        lambda _url: {
            "campaigns": 0,
            "artifacts": 0,
            "observations": 0,
            "hypothesis_snapshots": 0,
            "advisory_focus_snapshots": 0,
            "pentagi_flow_bindings": 0,
        },
    )
    monkeypatch.setattr(
        "app.production_migration._target_redis_count",
        lambda _queue: 0,
    )

    result = plan_migration()

    assert result["ok"] is False
    assert "source_queue_has_running_jobs" in result["blockers"]


def test_plan_blocks_nonempty_targets(monkeypatch, tmp_path):
    _configure_source(monkeypatch, tmp_path)

    monkeypatch.setattr(
        "app.production_migration._initialize_targets",
        lambda: (_FakePostgres(), _FakeQueue()),
    )
    monkeypatch.setattr(
        "app.production_migration._postgres_counts",
        lambda _url: {
            "campaigns": 1,
            "artifacts": 0,
            "observations": 0,
            "hypothesis_snapshots": 0,
            "advisory_focus_snapshots": 0,
            "pentagi_flow_bindings": 0,
        },
    )
    monkeypatch.setattr(
        "app.production_migration._target_redis_count",
        lambda _queue: 3,
    )

    result = plan_migration()

    assert result["ok"] is False
    assert set(result["blockers"]) == {
        "target_postgres_not_empty",
        "target_redis_queue_not_empty",
    }


def test_artifact_verification_detects_tampering(tmp_path):
    db_path = tmp_path / "xbow.sqlite3"
    artifact_root = tmp_path / "artifacts"
    store = Storage(db_path=str(db_path), artifact_root=str(artifact_root))
    store.save_campaign(_campaign(), expected_version=0)
    artifact = store.put_artifact(
        "campaign-1",
        "report",
        b"trusted report",
        media_type="text/plain",
    )

    metadata = store.get_artifact("campaign-1", artifact["id"])
    assert metadata is not None
    path = artifact_root / metadata["relative_path"]
    path.write_bytes(b"tampered")

    import sqlite3

    with sqlite3.connect(str(db_path)) as db:
        db.row_factory = sqlite3.Row
        with pytest.raises(ProductionMigrationError, match="artifact size mismatch|SHA-256 mismatch"):
            _verify_artifacts(db, artifact_root.resolve())


def test_artifact_verification_accepts_matching_content(tmp_path):
    db_path = tmp_path / "xbow.sqlite3"
    artifact_root = tmp_path / "artifacts"
    store = Storage(db_path=str(db_path), artifact_root=str(artifact_root))
    store.save_campaign(_campaign(), expected_version=0)
    payload = b"trusted evidence"
    artifact = store.put_artifact(
        "campaign-1",
        "http_evidence",
        payload,
        media_type="text/plain",
    )

    assert artifact["sha256"] == hashlib.sha256(payload).hexdigest()

    import sqlite3

    with sqlite3.connect(str(db_path)) as db:
        db.row_factory = sqlite3.Row
        result = _verify_artifacts(db, artifact_root.resolve())

    assert result == {"ok": True, "checked": 1}


def test_production_migration_cli_plan_returns_nonzero_when_blocked(monkeypatch, capsys):
    monkeypatch.setattr(
        production_migration_module,
        "plan_migration",
        lambda: {"ok": False, "blockers": ["blocked"]},
    )
    monkeypatch.setattr("sys.argv", ["production_migration", "plan"])

    assert production_migration_module.main() == 2
    assert '"ok": false' in capsys.readouterr().out


def test_production_migration_cli_plan_returns_zero_when_ready(monkeypatch, capsys):
    monkeypatch.setattr(
        production_migration_module,
        "plan_migration",
        lambda: {"ok": True, "blockers": []},
    )
    monkeypatch.setattr("sys.argv", ["production_migration", "plan"])

    assert production_migration_module.main() == 0
    assert '"ok": true' in capsys.readouterr().out
