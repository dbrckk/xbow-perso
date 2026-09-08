from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

TERMINAL = {"completed", "failed", "cancelled"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobQueue:
    """Small durable SQLite queue for self-hosted single-node deployments.

    Jobs contain only validated execution plans, never arbitrary shell strings.
    Workers claim jobs atomically. A future Redis/Postgres adapter can preserve
    this interface without weakening scope checks in the API/worker layers.
    """

    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("XBOW_DB_PATH", "/data/xbow.sqlite3")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout=30000")
            yield db
        finally:
            db.close()

    def _init(self) -> None:
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, kind TEXT NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 2,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                claimed_by TEXT, last_error TEXT
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at)")

    def enqueue(self, campaign_id: str, kind: str, payload: dict[str, Any], max_attempts: int = 2) -> dict[str, Any]:
        if kind not in {"strix_scan", "independent_validation", "report"}:
            raise ValueError("unsupported job kind")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be 1..5")
        job_id, now = str(uuid4()), utcnow()
        with self.connect() as db:
            db.execute("INSERT INTO jobs(id,campaign_id,kind,payload,status,max_attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                       (job_id, campaign_id, kind, json.dumps(payload), "queued", max_attempts, now, now))
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._decode(row) if row else None

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        if not worker_id.strip():
            raise ValueError("worker_id required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM jobs WHERE status='queued' AND attempts < max_attempts ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                db.execute("COMMIT")
                return None
            now = utcnow()
            db.execute("UPDATE jobs SET status='running', attempts=attempts+1, claimed_by=?, updated_at=? WHERE id=? AND status='queued'",
                       (worker_id, now, row["id"]))
            claimed = db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            db.execute("COMMIT")
        return self._decode(claimed)

    def finish(self, job_id: str, success: bool, error: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            if row["status"] != "running":
                raise ValueError("only running jobs can finish")
            status = "completed" if success else ("queued" if row["attempts"] < row["max_attempts"] else "failed")
            db.execute("UPDATE jobs SET status=?, updated_at=?, last_error=? WHERE id=?", (status, utcnow(), (error or "")[-4000:] or None, job_id))
        return self.get(job_id)  # type: ignore[return-value]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result
