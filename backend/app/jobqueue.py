from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .queue_audit import build_transition_event, verify_transition_events
from .queue_recovery import analyze_queue_recovery

TERMINAL = {"completed", "failed", "cancelled"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_identifier(value: str, name: str, *, max_length: int = 200) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be blank")
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
            db.execute("""CREATE TABLE IF NOT EXISTS job_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                seq INTEGER NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                at TEXT NOT NULL,
                previous_hash TEXT,
                event_hash TEXT NOT NULL,
                UNIQUE(job_id, seq)
            )""")
            db.execute(
                "CREATE INDEX IF NOT EXISTS job_transitions_campaign ON job_transitions(campaign_id, id)"
            )

    def _append_transition(
        self,
        db: sqlite3.Connection,
        row: sqlite3.Row | dict[str, Any],
        *,
        from_status: str | None,
        to_status: str,
        actor: str,
        reason: str,
        at: str,
    ) -> dict[str, Any]:
        job_id = str(row["id"])
        latest = db.execute(
            "SELECT seq,event_hash,to_status FROM job_transitions WHERE job_id=? ORDER BY seq DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        seq = int(latest["seq"]) + 1 if latest else 1
        previous_hash = str(latest["event_hash"]) if latest else None
        if latest and latest["to_status"] != from_status:
            raise RuntimeError("queue transition audit status discontinuity")
        event = build_transition_event(
            job_id=job_id,
            campaign_id=str(row["campaign_id"]),
            kind=str(row["kind"]),
            seq=seq,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            reason=reason,
            at=at,
            previous_hash=previous_hash,
        )
        db.execute(
            """INSERT INTO job_transitions(
                   job_id,campaign_id,kind,seq,from_status,to_status,actor,reason,at,previous_hash,event_hash
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event["job_id"],
                event["campaign_id"],
                event["kind"],
                event["seq"],
                event["from_status"],
                event["to_status"],
                event["actor"],
                event["reason"],
                event["at"],
                event["previous_hash"],
                event["event_hash"],
            ),
        )
        return event

    def job_transitions(self, job_id: str) -> list[dict[str, Any]]:
        job_id = _bounded_identifier(job_id, "job_id")
        with self.connect() as db:
            rows = db.execute(
                """SELECT job_id,campaign_id,kind,seq,from_status,to_status,actor,reason,at,previous_hash,event_hash
                   FROM job_transitions WHERE job_id=? ORDER BY seq""",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def verify_job_transitions(self, job_id: str) -> dict[str, Any]:
        events = self.job_transitions(job_id)
        verification = verify_transition_events(events)
        current = self.get(job_id)
        if current is None:
            return {**verification, "valid": False, "reason": "job missing"}
        if verification["valid"] and verification.get("final_status") != current["status"]:
            return {
                **verification,
                "valid": False,
                "reason": "audit final status does not match job status",
            }
        return verification

    def campaign_transition_audit(self, campaign_id: str) -> dict[str, Any]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        with self.connect() as db:
            job_ids = [
                row["id"]
                for row in db.execute(
                    "SELECT id FROM jobs WHERE campaign_id=? ORDER BY created_at,id",
                    (campaign_id,),
                ).fetchall()
            ]
        invalid: list[dict[str, Any]] = []
        checked_events = 0
        for job_id in job_ids:
            result = self.verify_job_transitions(job_id)
            checked_events += int(result.get("checked", 0))
            if not result.get("valid"):
                invalid.append({"job_id": job_id, "reason": result.get("reason")})
        return {
            "campaign_id": campaign_id,
            "jobs": len(job_ids),
            "events": checked_events,
            "valid": not invalid,
            "invalid_jobs": invalid,
        }

    def recovery_assessment(self) -> dict[str, Any]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT id,campaign_id,kind,status,attempts,max_attempts,
                          claimed_by,claimed_at,created_at,updated_at
                   FROM jobs ORDER BY created_at,id"""
            ).fetchall()
        jobs = [dict(row) for row in rows]
        audits = {
            str(job["id"]): self.verify_job_transitions(str(job["id"]))
            for job in jobs
        }
        return {
            **analyze_queue_recovery(
                jobs,
                lease_seconds=_job_lease_seconds(),
                audit_results=audits,
            ),
            "storage": "sqlite",
        }

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
        if kind not in {"strix_scan", "nuclei_scan", "independent_validation", "browser_flow", "recon_task", "report", "pentagi_flow", "pentagi_status"}:
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
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    """INSERT INTO jobs(
                           id,campaign_id,kind,payload,status,max_attempts,created_at,updated_at,dedupe_key
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (job_id, campaign_id, kind, encoded_payload, "queued", max_attempts, now, now, dedupe_key),
                )
                row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
                self._append_transition(
                    db,
                    row,
                    from_status=None,
                    to_status="queued",
                    actor="queue",
                    reason="job enqueued",
                    at=now,
                )
                db.execute("COMMIT")
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

    def get_by_dedupe(
        self,
        campaign_id: str,
        kind: str,
        dedupe_key: str,
    ) -> dict[str, Any] | None:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        kind = _bounded_identifier(kind, "kind")
        dedupe_key = _bounded_identifier(dedupe_key, "dedupe_key")
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE campaign_id=? AND kind=? AND dedupe_key=?",
                (campaign_id, kind, dedupe_key),
            ).fetchone()
        return self._decode(row) if row else None

    def stats(self) -> dict[str, Any]:
        """Return bounded operational queue telemetry without exposing payloads."""
        with self.connect() as db:
            rows = db.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
            total = db.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"]
            oldest = db.execute(
                "SELECT created_at FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            oldest_running = db.execute(
                "SELECT claimed_at FROM jobs WHERE status='running' AND claimed_at IS NOT NULL ORDER BY claimed_at LIMIT 1"
            ).fetchone()
        counts = {status: 0 for status in ("queued", "running", "completed", "failed", "cancelled")}
        counts.update({row["status"]: row["count"] for row in rows})
        return {
            "total": total,
            "by_status": counts,
            "oldest_queued_at": oldest["created_at"] if oldest else None,
            "oldest_running_claimed_at": (
                oldest_running["claimed_at"] if oldest_running else None
            ),
        }

    def campaign_job_counts(self, campaign_id: str) -> dict[str, int]:
        """Return durable job counts for one campaign without exposing payloads."""
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        with self.connect() as db:
            rows = db.execute(
                "SELECT kind, COUNT(*) AS count FROM jobs WHERE campaign_id=? GROUP BY kind",
                (campaign_id,),
            ).fetchall()
        counts = {kind: 0 for kind in ("strix_scan", "nuclei_scan", "independent_validation", "browser_flow", "recon_task", "report", "pentagi_flow", "pentagi_status")}
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
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM jobs WHERE campaign_id=? AND status='queued' ORDER BY created_at,id",
                (campaign_id,),
            ).fetchall()
            for row in rows:
                cursor = db.execute(
                    """UPDATE jobs
                       SET status='cancelled', updated_at=?, claimed_by=NULL, claimed_at=NULL,
                           last_error='campaign cancelled before execution'
                       WHERE id=? AND status='queued'""",
                    (now, row["id"]),
                )
                if cursor.rowcount == 1:
                    self._append_transition(
                        db,
                        row,
                        from_status="queued",
                        to_status="cancelled",
                        actor="campaign-control",
                        reason="campaign cancelled before execution",
                        at=now,
                    )
            db.execute("COMMIT")
        return len(rows)

    def cancel_owned(self, job_id: str, worker_id: str, reason: str = "campaign cancelled") -> dict[str, Any] | None:
        """Cancel a running job only when the caller still owns its lease."""
        job_id = _bounded_identifier(job_id, "job_id")
        worker_id = _bounded_identifier(worker_id, "worker_id")
        reason = reason.strip()
        if len(reason) > 4000:
            reason = reason[-4000:]
        if any(ord(ch) < 32 and ch not in "\t" for ch in reason):
            raise ValueError("cancel reason contains invalid characters")
        now = utcnow()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE id=? AND status='running' AND claimed_by=?",
                (job_id, worker_id),
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return None
            cursor = db.execute(
                """UPDATE jobs
                   SET status='cancelled', updated_at=?, last_error=?,
                       claimed_by=NULL, claimed_at=NULL
                   WHERE id=? AND status='running' AND claimed_by=?""",
                (now, reason[-4000:] or None, job_id, worker_id),
            )
            if cursor.rowcount == 1:
                self._append_transition(
                    db,
                    row,
                    from_status="running",
                    to_status="cancelled",
                    actor=worker_id,
                    reason=reason or "campaign cancelled",
                    at=now,
                )
            db.execute("COMMIT")
        if cursor.rowcount != 1:
            return None
        return self.get(job_id)

    def _recover_expired_leases(self, db: sqlite3.Connection, now: datetime) -> int:
        lease_seconds = _job_lease_seconds()
        cutoff = (now - timedelta(seconds=lease_seconds)).isoformat()
        stale = db.execute(
            "SELECT * FROM jobs WHERE status='running' AND claimed_at IS NOT NULL AND claimed_at < ?",
            (cutoff,),
        ).fetchall()
        for row in stale:
            exhausted = row["attempts"] >= row["max_attempts"]
            status = "failed" if exhausted else "queued"
            cursor = db.execute(
                """UPDATE jobs
                   SET status=?, updated_at=?, claimed_by=NULL, claimed_at=NULL,
                       last_error='worker lease expired before completion'
                   WHERE id=? AND status='running'""",
                (status, now.isoformat(), row["id"]),
            )
            if cursor.rowcount == 1:
                self._append_transition(
                    db,
                    row,
                    from_status="running",
                    to_status=status,
                    actor="lease-recovery",
                    reason="worker lease expired before completion",
                    at=now.isoformat(),
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
                "SELECT * FROM jobs WHERE status='queued' AND kind NOT IN ('pentagi_flow','pentagi_status') AND attempts < max_attempts ORDER BY created_at,id LIMIT 1"
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return None
            now = now_dt.isoformat()
            cursor = db.execute(
                """UPDATE jobs
                   SET status='running', attempts=attempts+1, claimed_by=?, claimed_at=?, updated_at=?
                   WHERE id=? AND status='queued'""",
                (worker_id, now, now, row["id"]),
            )
            if cursor.rowcount != 1:
                db.execute("ROLLBACK")
                return None
            self._append_transition(
                db,
                row,
                from_status="queued",
                to_status="running",
                actor=worker_id,
                reason="job claimed",
                at=now,
            )
            claimed = db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            db.execute("COMMIT")
        return self._decode(claimed)

    def claim_allowed(self, worker_id: str, kinds: tuple[str, ...] | list[str]) -> dict[str, Any] | None:
        """Atomically claim the oldest queued job among an explicit set of kinds."""
        worker_id = _bounded_identifier(worker_id, "worker_id")
        allowed_kinds = {
            "strix_scan",
            "nuclei_scan",
            "independent_validation",
            "browser_flow",
            "recon_task",
            "report",
            "pentagi_flow",
            "pentagi_status",
        }
        normalized = tuple(dict.fromkeys(_bounded_identifier(kind, "kind") for kind in kinds))
        if not normalized:
            raise ValueError("at least one allowed job kind is required")
        if any(kind not in allowed_kinds for kind in normalized):
            raise ValueError("unsupported job kind")
        placeholders = ",".join("?" for _ in normalized)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now_dt = datetime.now(timezone.utc)
            self._recover_expired_leases(db, now_dt)
            row = db.execute(
                f"SELECT * FROM jobs WHERE status='queued' AND kind IN ({placeholders}) "
                "AND attempts < max_attempts ORDER BY created_at,id LIMIT 1",
                normalized,
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return None
            now = now_dt.isoformat()
            cursor = db.execute(
                """UPDATE jobs
                   SET status='running', attempts=attempts+1, claimed_by=?, claimed_at=?, updated_at=?
                   WHERE id=? AND status='queued'""",
                (worker_id, now, now, row["id"]),
            )
            if cursor.rowcount != 1:
                db.execute("ROLLBACK")
                return None
            self._append_transition(
                db,
                row,
                from_status="queued",
                to_status="running",
                actor=worker_id,
                reason="job claimed",
                at=now,
            )
            claimed = db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            db.execute("COMMIT")
        return self._decode(claimed)

    def claim_kind(self, worker_id: str, kind: str) -> dict[str, Any] | None:
        """Atomically claim only one explicitly requested job kind."""
        worker_id = _bounded_identifier(worker_id, "worker_id")
        kind = _bounded_identifier(kind, "kind")
        allowed_kinds = {"strix_scan", "nuclei_scan", "independent_validation", "browser_flow", "recon_task", "report", "pentagi_flow", "pentagi_status"}
        if kind not in allowed_kinds:
            raise ValueError("unsupported job kind")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now_dt = datetime.now(timezone.utc)
            self._recover_expired_leases(db, now_dt)
            row = db.execute(
                "SELECT * FROM jobs WHERE status='queued' AND kind=? AND attempts < max_attempts ORDER BY created_at,id LIMIT 1",
                (kind,),
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return None
            now = now_dt.isoformat()
            cursor = db.execute(
                """UPDATE jobs
                   SET status='running', attempts=attempts+1, claimed_by=?, claimed_at=?, updated_at=?
                   WHERE id=? AND status='queued' AND kind=?""",
                (worker_id, now, now, row["id"], kind),
            )
            if cursor.rowcount != 1:
                db.execute("ROLLBACK")
                return None
            self._append_transition(
                db,
                row,
                from_status="queued",
                to_status="running",
                actor=worker_id,
                reason="job claimed",
                at=now,
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
        """Finish a job only if the caller still owns its running lease."""
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
            reason = (
                "job completed"
                if success
                else ("job requeued after failure" if status == "queued" else "job failed")
            )
            cursor = db.execute(
                """UPDATE jobs
                   SET status=?, updated_at=?, last_error=?, claimed_by=NULL, claimed_at=NULL
                   WHERE id=? AND status='running' AND claimed_by=?""",
                (status, now, (error or "")[-4000:] or None, job_id, worker_id),
            )
            if cursor.rowcount == 1:
                self._append_transition(
                    db,
                    row,
                    from_status="running",
                    to_status=status,
                    actor=worker_id,
                    reason=reason,
                    at=now,
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
