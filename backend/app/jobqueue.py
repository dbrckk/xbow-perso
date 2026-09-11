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


def _bounded_identifier(value: str, name: str, *, max_length: int = 200) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} required")
    if len(normalized) > max_length:
        raise ValueError(f"{name} too long")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in normalized):
        raise ValueError(f"{name} contains invalid characters")
    return normalized


def _job_lease_seconds() -> int:
    raw = os.getenv("XBOW_JOB_LEASE_SECONDS", "21600")
    try:
        lease_seconds = int(raw)
    except ValueError as exc:
        raise ValueError("XBOW_JOB_LEASE_SECONDS must be an integer") from exc
    if not 60 <= lease_seconds <= 86400:
        raise ValueError("XBOW_JOB_LEASE_SECONDS must be between 60 and 86400")
    return lease_seconds


def _harden_db_permissions(path: Path) -> None:
    if os.name != "posix" or not path.exists():
        return
    try:
        path.chmod(0o600)
    except OSError as exc:
        raise RuntimeError("unable to enforce private queue database permissions") from exc


def _max_job_payload_bytes() -> int:
    raw = os.getenv("XBOW_MAX_JOB_PAYLOAD_BYTES", "65536")
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError("XBOW_MAX_JOB_PAYLOAD_BYTES must be an integer") from exc
    if not 1024 <= limit <= 1024 * 1024:
        raise ValueError("XBOW_MAX_JOB_PAYLOAD_BYTES must be between 1 KiB and 1 MiB")
    return limit


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
        _harden_db_permissions(Path(self.path))

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
                claimed_by TEXT, claimed_at TEXT, last_error TEXT, dedupe_key TEXT
            )""")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
            if "claimed_at" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN claimed_at TEXT")
            if "dedupe_key" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN dedupe_key TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_running_claimed ON jobs(status, claimed_at)")
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS jobs_dedupe ON jobs(campaign_id,kind,dedupe_key) WHERE dedupe_key IS NOT NULL"
            )

    def health(self) -> dict[str, Any]:
        """Return minimal storage health without exposing job payloads."""
        try:
            with self.connect() as db:
                quick_check = db.execute("PRAGMA quick_check").fetchone()[0]
                count = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        except sqlite3.Error as exc:
            return {"ok": False, "storage": "sqlite", "error": exc.__class__.__name__}
        return {
            "ok": quick_check == "ok",
            "storage": "sqlite",
            "integrity": quick_check,
            "jobs": int(count),
        }

    def enqueue(
        self,
        campaign_id: str,
        kind: str,
        payload: dict[str, Any],
        max_attempts: int = 2,
        *,
        dedupe_key: str | None = None,
    ) -> dict[str, Any]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        if kind not in {"strix_scan", "independent_validation", "browser_flow", "report"}:
            raise ValueError("unsupported job kind")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be 1..5")
        if dedupe_key is not None:
            dedupe_key = _bounded_identifier(dedupe_key, "dedupe_key")

        encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded_payload.encode("utf-8")) > _max_job_payload_bytes():
            raise ValueError("job payload exceeds size limit")
        if dedupe_key is not None:
            with self.connect() as db:
                existing = db.execute(
                    "SELECT * FROM jobs WHERE campaign_id=? AND kind=? AND dedupe_key=?",
                    (campaign_id, kind, dedupe_key),
                ).fetchone()
            if existing:
                decoded = self._decode(existing)
                if json.dumps(decoded["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False) != encoded_payload:
                    raise ValueError("dedupe_key reused with different job payload")
                return decoded

        job_id, now = str(uuid4()), utcnow()
        try:
            with self.connect() as db:
                db.execute(
                    """INSERT INTO jobs(
                           id,campaign_id,kind,payload,status,max_attempts,created_at,updated_at,dedupe_key
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (job_id, campaign_id, kind, encoded_payload, "queued", max_attempts, now, now, dedupe_key),
                )
        except sqlite3.IntegrityError:
            if dedupe_key is None:
                raise
            with self.connect() as db:
                existing = db.execute(
                    "SELECT * FROM jobs WHERE campaign_id=? AND kind=? AND dedupe_key=?",
                    (campaign_id, kind, dedupe_key),
                ).fetchone()
            if not existing:
                raise
            decoded = self._decode(existing)
            if json.dumps(decoded["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False) != encoded_payload:
                raise ValueError("dedupe_key reused with different job payload")
            return decoded
        result = self.get(job_id)
        if result is None:
            raise RuntimeError("queued job disappeared")
        return result

    def get(self, job_id: str) -> dict[str, Any] | None:
        job_id = _bounded_identifier(job_id, "job_id")
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

    def campaign_job_counts(self, campaign_id: str) -> dict[str, int]:
        """Return durable job counts for one campaign without exposing payloads."""
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        with self.connect() as db:
            rows = db.execute(
                "SELECT kind, COUNT(*) AS count FROM jobs WHERE campaign_id=? GROUP BY kind",
                (campaign_id,),
            ).fetchall()
        counts = {kind: 0 for kind in ("strix_scan", "independent_validation", "browser_flow", "report")}
        counts.update({row["kind"]: int(row["count"]) for row in rows})
        return counts

    def campaign_job_status_counts(self, campaign_id: str) -> dict[str, int]:
        """Return per-status job counts for one campaign without exposing payloads."""
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        with self.connect() as db:
            rows = db.execute(
                "SELECT status, COUNT(*) AS count FROM jobs WHERE campaign_id=? GROUP BY status",
                (campaign_id,),
            ).fetchall()
        counts = {status: 0 for status in ("queued", "running", "completed", "failed", "cancelled")}
        counts.update({row["status"]: int(row["count"]) for row in rows})
        return counts

    def cancel_queued(self, campaign_id: str) -> int:
        """Cancel queued jobs for a campaign without stealing running leases."""
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        now = utcnow()
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE jobs
                   SET status='cancelled', updated_at=?, claimed_by=NULL, claimed_at=NULL,
                       last_error='campaign cancelled before execution'
                   WHERE campaign_id=? AND status='queued'""",
                (now, campaign_id),
            )
        return int(cursor.rowcount)

    def cancel_owned(self, job_id: str, worker_id: str, reason: str = "campaign cancelled") -> dict[str, Any] | None:
        """Cancel a running job only when the caller still owns its lease."""
        job_id = _bounded_identifier(job_id, "job_id")
        worker_id = _bounded_identifier(worker_id, "worker_id")
        reason = reason.strip()
        if len(reason) > 4000:
            reason = reason[-4000:]
        if any(ord(ch) < 32 and ch not in "\t" for ch in reason):
            raise ValueError("cancel reason contains invalid characters")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                """UPDATE jobs
                   SET status='cancelled', updated_at=?, last_error=?,
                       claimed_by=NULL, claimed_at=NULL
                   WHERE id=? AND status='running' AND claimed_by=?""",
                (utcnow(), reason[-4000:] or None, job_id, worker_id),
            )
            db.execute("COMMIT")
        if cursor.rowcount != 1:
            return None
        return self.get(job_id)

    def _recover_expired_leases(self, db: sqlite3.Connection, now: datetime) -> int:
        lease_seconds = _job_lease_seconds()
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
        worker_id = _bounded_identifier(worker_id, "worker_id")
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
        """Renew a running job lease only when the caller still owns it."""
        job_id = _bounded_identifier(job_id, "job_id")
        worker_id = _bounded_identifier(worker_id, "worker_id")
        now = utcnow()
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE jobs SET claimed_at=?, updated_at=?
                   WHERE id=? AND status='running' AND claimed_by=?""",
                (now, now, job_id, worker_id),
            )
        return cursor.rowcount == 1

    def finish(
        self,
        job_id: str,
        worker_id: str,
        success: bool,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        """Finish a job only if the caller still owns its running lease.

        Returns None when ownership has already been lost. This prevents a stale
        worker from completing or requeueing work that another worker has claimed.
        """
        job_id = _bounded_identifier(job_id, "job_id")
        worker_id = _bounded_identifier(worker_id, "worker_id")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE id=? AND status='running' AND claimed_by=?",
                (job_id, worker_id),
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return None
            status = "completed" if success else ("queued" if row["attempts"] < row["max_attempts"] else "failed")
            now = utcnow()
            cursor = db.execute(
                """UPDATE jobs
                   SET status=?, updated_at=?, last_error=?, claimed_by=NULL, claimed_at=NULL
                   WHERE id=? AND status='running' AND claimed_by=?""",
                (status, now, (error or "")[-4000:] or None, job_id, worker_id),
            )
            db.execute("COMMIT")
        if cursor.rowcount != 1:
            return None
        return self.get(job_id)

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result
