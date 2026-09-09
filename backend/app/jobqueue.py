from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

TERMINAL = {"completed", "failed", "cancelled"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobQueue:
    """Small durable SQLite queue for self-hosted single-node deployments.

    Jobs contain only validated execution plans, never arbitrary shell strings.
    Workers claim jobs atomically. Running jobs use a durable lease so a worker
    crash cannot strand a campaign forever; expired leases are recovered on the
    next claim without bypassing retry limits.
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
                claimed_by TEXT, claimed_at TEXT, last_error TEXT
            )""")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
            if "claimed_at" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN claimed_at TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_running_claimed ON jobs(status, claimed_at)")

    def enqueue(self, campaign_id: str, kind: str, payload: dict[str, Any], max_attempts: int = 2) -> dict[str, Any]:
        if kind not in {"strix_scan", "independent_validation", "browser_flow", "report"}:
            raise ValueError("unsupported job kind")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be 1..5")
        job_id, now = str(uuid4()), utcnow()
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs(id,campaign_id,kind,payload,status,max_attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (job_id, campaign_id, kind, json.dumps(payload), "queued", max_attempts, now, now),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._decode(row) if row else None

    def stats(self) -> dict[str, Any]:
        """Return bounded operational queue telemetry without exposing payloads."""
        with self.connect() as db:
            rows = db.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
            total = db.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"]
            oldest = db.execute(
                "SELECT created_at FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
        counts = {status: 0 for status in ("queued", "running", "completed", "failed", "cancelled")}
        counts.update({row["status"]: row["count"] for row in rows})
        return {
            "total": total,
            "by_status": counts,
            "oldest_queued_at": oldest["created_at"] if oldest else None,
        }

    def _recover_expired_leases(self, db: sqlite3.Connection, now: datetime) -> int:
        lease_seconds = int(os.getenv("XBOW_JOB_LEASE_SECONDS", "21600"))
        if not 60 <= lease_seconds <= 86400:
            raise ValueError("XBOW_JOB_LEASE_SECONDS must be between 60 and 86400")
        cutoff = (now - timedelta(seconds=lease_seconds)).isoformat()
        stale = db.execute(
            "SELECT id,attempts,max_attempts FROM jobs WHERE status='running' AND claimed_at IS NOT NULL AND claimed_at < ?",
            (cutoff,),
        ).fetchall()
        for row in stale:
            exhausted = row["attempts"] >= row["max_attempts"]
            status = "failed" if exhausted else "queued"
            db.execute(
                """UPDATE jobs
                   SET status=?, updated_at=?, claimed_by=NULL, claimed_at=NULL,
                       last_error='worker lease expired before completion'
                   WHERE id=? AND status='running'""",
                (status, now.isoformat(), row["id"]),
            )
        return len(stale)

    def recover_expired_leases(self) -> int:
        """Recover jobs abandoned by dead workers while respecting max_attempts."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = self._recover_expired_leases(db, datetime.now(timezone.utc))
            db.execute("COMMIT")
        return count

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        if not worker_id.strip():
            raise ValueError("worker_id required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now_dt = datetime.now(timezone.utc)
            self._recover_expired_leases(db, now_dt)
            row = db.execute(
                "SELECT id FROM jobs WHERE status='queued' AND attempts < max_attempts ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return None
            now = now_dt.isoformat()
            db.execute(
                """UPDATE jobs
                   SET status='running', attempts=attempts+1, claimed_by=?, claimed_at=?, updated_at=?
                   WHERE id=? AND status='queued'""",
                (worker_id, now, now, row["id"]),
            )
            claimed = db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            db.execute("COMMIT")
        return self._decode(claimed)

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        """Renew a running job lease only when the caller still owns it.

        Returning False is deliberate fail-closed behaviour: a worker that lost
        ownership must not silently extend another worker's lease.
        """
        if not worker_id.strip():
            raise ValueError("worker_id required")
        now = utcnow()
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE jobs SET claimed_at=?, updated_at=?
                   WHERE id=? AND status='running' AND claimed_by=?""",
                (now, now, job_id, worker_id),
            )
        return cursor.rowcount == 1

    def finish(self, job_id: str, success: bool, error: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            if row["status"] != "running":
                raise ValueError("only running jobs can finish")
            status = "completed" if success else ("queued" if row["attempts"] < row["max_attempts"] else "failed")
            db.execute(
                """UPDATE jobs
                   SET status=?, updated_at=?, last_error=?, claimed_by=NULL, claimed_at=NULL
                   WHERE id=?""",
                (status, utcnow(), (error or "")[-4000:] or None, job_id),
            )
        return self.get(job_id)  # type: ignore[return-value]

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result
