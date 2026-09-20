from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
import redis

from .postgres_storage import PostgresStorage
from .redis_jobqueue import RedisJobQueue, _uses_generic_queue


_CORE_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "campaigns",
        ("id", "document", "state", "created_at", "updated_at", "version"),
    ),
    (
        "artifacts",
        (
            "id",
            "campaign_id",
            "finding_id",
            "kind",
            "media_type",
            "relative_path",
            "sha256",
            "size_bytes",
            "created_at",
            "idempotency_key",
        ),
    ),
    (
        "observations",
        (
            "campaign_id",
            "id",
            "kind",
            "value",
            "source",
            "parent_ids",
            "metadata",
            "created_at",
        ),
    ),
    (
        "hypothesis_snapshots",
        ("campaign_id", "graph_fingerprint", "document", "created_at"),
    ),
    (
        "advisory_focus_snapshots",
        ("campaign_id", "fingerprint", "document", "created_at"),
    ),
    (
        "pentagi_flow_bindings",
        (
            "flow_id",
            "campaign_id",
            "policy_fingerprint",
            "endpoint",
            "model_provider",
            "created_at",
        ),
    ),
)

_JOB_COLUMNS = (
    "id",
    "campaign_id",
    "kind",
    "payload",
    "status",
    "attempts",
    "max_attempts",
    "created_at",
    "updated_at",
    "claimed_by",
    "claimed_at",
    "last_error",
    "dedupe_key",
)


class ProductionMigrationError(RuntimeError):
    pass


def _bool_env(name: str) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ProductionMigrationError(f"{name} must be a boolean")


def _source_path() -> Path:
    path = Path(os.getenv("XBOW_MIGRATION_SQLITE_PATH", os.getenv("XBOW_DB_PATH", "/data/xbow.sqlite3")))
    if path.is_symlink() or not path.is_file():
        raise ProductionMigrationError("source SQLite database is unavailable")
    return path


def _artifact_root() -> Path:
    root = Path(os.getenv("XBOW_ARTIFACT_ROOT", "/data/artifacts"))
    if root.is_symlink() or not root.is_dir():
        raise ProductionMigrationError("artifact root is unavailable")
    return root.resolve()


def _database_url() -> str:
    value = (os.getenv("XBOW_DATABASE_URL") or "").strip()
    if not value.startswith(("postgresql://", "postgres://")):
        raise ProductionMigrationError("XBOW_DATABASE_URL must be configured for PostgreSQL")
    return value


def _redis_url() -> str:
    value = (os.getenv("XBOW_REDIS_URL") or "").strip()
    if not value.startswith(("redis://", "rediss://")):
        raise ProductionMigrationError("XBOW_REDIS_URL must be configured for Redis")
    return value


def _connect_source(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _table_exists(db: sqlite3.Connection, table: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _source_counts(db: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, _columns in _CORE_TABLES:
        counts[table] = (
            int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            if _table_exists(db, table)
            else 0
        )
    counts["jobs"] = (
        int(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
        if _table_exists(db, "jobs")
        else 0
    )
    return counts


def _queue_status(db: sqlite3.Connection) -> dict[str, int]:
    counts = {status: 0 for status in ("queued", "running", "completed", "failed", "cancelled")}
    if not _table_exists(db, "jobs"):
        return counts
    for row in db.execute("SELECT status,COUNT(*) AS count FROM jobs GROUP BY status"):
        status = str(row["status"])
        if status in counts:
            counts[status] = int(row["count"])
    return counts


def _verify_artifacts(db: sqlite3.Connection, root: Path) -> dict[str, Any]:
    checked = 0
    if not _table_exists(db, "artifacts"):
        return {"ok": True, "checked": 0}
    for row in db.execute(
        "SELECT relative_path,sha256,size_bytes FROM artifacts ORDER BY id"
    ):
        candidate = (root / str(row["relative_path"])).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ProductionMigrationError("artifact path escapes configured root") from exc
        if not candidate.is_file():
            raise ProductionMigrationError("artifact content is missing")
        content = candidate.read_bytes()
        if len(content) != int(row["size_bytes"]):
            raise ProductionMigrationError("artifact size mismatch")
        if hashlib.sha256(content).hexdigest() != str(row["sha256"]):
            raise ProductionMigrationError("artifact SHA-256 mismatch")
        checked += 1
    return {"ok": True, "checked": checked}


def _initialize_targets() -> tuple[PostgresStorage, RedisJobQueue]:
    postgres = PostgresStorage(database_url=_database_url(), artifact_root=str(_artifact_root()))
    with postgres.connect() as db:
        postgres._ensure_pentagi_flow_bindings(db)
    queue = RedisJobQueue(url=_redis_url())
    if not queue.health().get("ok"):
        raise ProductionMigrationError("Redis target is unavailable")
    return postgres, queue


def _postgres_counts(url: str) -> dict[str, int]:
    result: dict[str, int] = {}
    with psycopg.connect(url, connect_timeout=10) as db:
        for table, _columns in _CORE_TABLES:
            try:
                row = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            except psycopg.errors.UndefinedTable:
                db.rollback()
                result[table] = 0
                continue
            result[table] = int(row[0])
    return result


def _target_redis_count(queue: RedisJobQueue) -> int:
    return int(queue.stats().get("total") or 0)


def plan_migration() -> dict[str, Any]:
    source = _source_path()
    root = _artifact_root()
    database_url = _database_url()
    _redis_url()

    with _connect_source(source) as db:
        counts = _source_counts(db)
        queue_status = _queue_status(db)
        artifacts = _verify_artifacts(db, root)

    postgres, queue = _initialize_targets()
    target_counts = _postgres_counts(database_url)
    redis_jobs = _target_redis_count(queue)

    blockers: list[str] = []
    if queue_status["running"]:
        blockers.append("source_queue_has_running_jobs")
    if any(target_counts.values()):
        blockers.append("target_postgres_not_empty")
    if redis_jobs:
        blockers.append("target_redis_queue_not_empty")

    return {
        "ok": not blockers,
        "source": {
            "sqlite_present": True,
            "counts": counts,
            "queue_by_status": queue_status,
            "artifacts": artifacts,
        },
        "target": {
            "postgres_ready": bool(postgres.health().get("ok")),
            "postgres_counts": target_counts,
            "redis_ready": bool(queue.health().get("ok")),
            "redis_jobs": redis_jobs,
        },
        "blockers": blockers,
        "requires_quiesced_apply": True,
        "copies_queue_history": True,
        "copies_artifact_metadata_only": True,
        "artifact_files_reused_in_place": True,
        "contains_secrets": False,
        "contains_payloads": False,
    }


def _backup_sqlite(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ProductionMigrationError("backup destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_db = sqlite3.connect(str(source))
    target_db = sqlite3.connect(str(destination))
    try:
        source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()
    try:
        destination.chmod(0o600)
    except OSError:
        pass


def _copy_postgres(source_db: sqlite3.Connection, url: str) -> dict[str, int]:
    copied: dict[str, int] = {}
    with psycopg.connect(url, connect_timeout=10) as target:
        with target.transaction():
            for table, columns in _CORE_TABLES:
                if not _table_exists(source_db, table):
                    copied[table] = 0
                    continue
                rows = source_db.execute(
                    f"SELECT {','.join(columns)} FROM {table}"
                ).fetchall()
                if rows:
                    placeholders = ",".join("%s" for _ in columns)
                    sql = (
                        f"INSERT INTO {table} ({','.join(columns)}) "
                        f"VALUES ({placeholders})"
                    )
                    target.executemany(sql, [tuple(row[column] for column in columns) for row in rows])
                copied[table] = len(rows)
    return copied


def _timestamp_score(value: str | None) -> float:
    if not value:
        return time.time()
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return time.time()


def _copy_redis_jobs(source_db: sqlite3.Connection, queue: RedisJobQueue) -> int:
    if not _table_exists(source_db, "jobs"):
        return 0
    rows = source_db.execute(
        f"SELECT {','.join(_JOB_COLUMNS)} FROM jobs ORDER BY created_at,id"
    ).fetchall()
    if not rows:
        return 0

    with queue.redis.pipeline(transaction=True) as pipe:
        for source_row in rows:
            row = {column: source_row[column] for column in _JOB_COLUMNS}
            job_id = str(row["id"])
            campaign_id = str(row["campaign_id"])
            kind = str(row["kind"])
            status = str(row["status"])
            encoded = {
                "id": job_id,
                "campaign_id": campaign_id,
                "kind": kind,
                "payload": str(row["payload"]),
                "status": status,
                "attempts": str(int(row["attempts"])),
                "max_attempts": str(int(row["max_attempts"])),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "claimed_by": str(row["claimed_by"] or ""),
                "claimed_at": str(row["claimed_at"] or ""),
                "last_error": str(row["last_error"] or ""),
                "dedupe_key": str(row["dedupe_key"] or ""),
            }
            pipe.hset(queue._job_key(job_id), mapping=encoded)
            pipe.sadd(queue._all, job_id)
            pipe.sadd(queue._campaign_key(campaign_id), job_id)
            if row["dedupe_key"]:
                pipe.hset(
                    queue._dedupe_key(campaign_id, kind),
                    str(row["dedupe_key"]),
                    job_id,
                )
            score = _timestamp_score(str(row["created_at"]))
            if status == "queued":
                if _uses_generic_queue(kind):
                    pipe.zadd(queue._queued, {job_id: score})
                pipe.zadd(queue._queued_kind(kind), {job_id: score})
            elif status == "running":
                raise ProductionMigrationError("running jobs cannot be migrated")
        pipe.execute()
    return len(rows)


def _clear_targets(url: str, queue: RedisJobQueue) -> None:
    # Safe only because apply refuses non-empty targets before writing.
    with psycopg.connect(url, connect_timeout=10) as db:
        with db.transaction():
            for table, _columns in reversed(_CORE_TABLES):
                try:
                    db.execute(f"DELETE FROM {table}")
                except psycopg.errors.UndefinedTable:
                    db.rollback()
                    break
    keys = list(queue.redis.scan_iter(match=f"{queue.prefix}:*"))
    if keys:
        queue.redis.delete(*keys)


def apply_migration() -> dict[str, Any]:
    if not _bool_env("XBOW_MIGRATION_QUIESCED"):
        raise ProductionMigrationError(
            "set XBOW_MIGRATION_QUIESCED=true only after backend/workers are stopped"
        )

    plan = plan_migration()
    if not plan["ok"]:
        raise ProductionMigrationError(
            "migration preflight blocked: " + ",".join(plan["blockers"])
        )

    source = _source_path()
    root = _artifact_root()
    url = _database_url()
    backup = Path(
        os.getenv(
            "XBOW_MIGRATION_BACKUP_PATH",
            str(source.with_name(source.name + ".pre-postgres.bak")),
        )
    )

    _backup_sqlite(source, backup)
    postgres, queue = _initialize_targets()

    try:
        with _connect_source(source) as source_db:
            copied = _copy_postgres(source_db, url)
            jobs = _copy_redis_jobs(source_db, queue)
            _verify_artifacts(source_db, root)
    except Exception:
        _clear_targets(url, queue)
        raise

    target_counts = _postgres_counts(url)
    expected_counts = dict(plan["source"]["counts"])
    for table, count in copied.items():
        if target_counts.get(table) != count:
            _clear_targets(url, queue)
            raise ProductionMigrationError(f"target verification failed for {table}")
    if _target_redis_count(queue) != jobs:
        _clear_targets(url, queue)
        raise ProductionMigrationError("target Redis job-count verification failed")

    return {
        "ok": True,
        "backup_created": True,
        "backup_filename": backup.name,
        "copied": copied,
        "jobs_copied": jobs,
        "artifacts_verified": int(plan["source"]["artifacts"]["checked"]),
        "postgres_ready": bool(postgres.health().get("ok")),
        "redis_ready": bool(queue.health().get("ok")),
        "source_unchanged": True,
        "contains_secrets": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.production_migration",
        description="Controlled SQLite/queue migration to PostgreSQL + Redis.",
    )
    parser.add_argument("command", choices=("plan", "apply"))
    args = parser.parse_args()
    try:
        result = plan_migration() if args.command == "plan" else apply_migration()
    except (ProductionMigrationError, OSError, sqlite3.Error, psycopg.Error, redis.RedisError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
