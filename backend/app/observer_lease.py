from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


class ObserverLease:
    """Small SQLite lease ensuring one active incident observer per shared DB."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init()

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _init(self):
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS incident_observer_lease (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    owner TEXT,
                    expires_at TEXT,
                    generation INTEGER NOT NULL DEFAULT 0
                )"""
            )
            db.execute(
                "INSERT OR IGNORE INTO incident_observer_lease(singleton, owner, expires_at, generation) VALUES(1, NULL, NULL, 0)"
            )

    def acquire(self, owner: str, *, ttl_seconds: int, now: datetime | None = None) -> int | None:
        if not owner or len(owner) > 128:
            raise ValueError("owner must contain 1..128 characters")
        if not 10 <= ttl_seconds <= 3600:
            raise ValueError("ttl_seconds must be between 10 and 3600")
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        expires = current + timedelta(seconds=ttl_seconds)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner, expires_at, generation FROM incident_observer_lease WHERE singleton = 1"
            ).fetchone()
            active_until = (
                datetime.fromisoformat(row["expires_at"])
                if row["expires_at"]
                else None
            )
            if row["owner"] not in (None, owner) and active_until and active_until > current:
                db.execute("ROLLBACK")
                return None
            generation = int(row["generation"]) + (0 if row["owner"] == owner else 1)
            db.execute(
                "UPDATE incident_observer_lease SET owner = ?, expires_at = ?, generation = ? WHERE singleton = 1",
                (owner, expires.isoformat(), generation),
            )
            db.execute("COMMIT")
        return generation

    def heartbeat(self, owner: str, generation: int, *, ttl_seconds: int, now: datetime | None = None) -> bool:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        expires = current + timedelta(seconds=ttl_seconds)
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE incident_observer_lease SET expires_at = ?
                   WHERE singleton = 1 AND owner = ? AND generation = ? AND expires_at > ?""",
                (expires.isoformat(), owner, generation, current.isoformat()),
            )
        return cursor.rowcount == 1

    def is_current(self, owner: str, generation: int, *, now: datetime | None = None) -> bool:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self._connect() as db:
            row = db.execute(
                "SELECT owner, generation, expires_at FROM incident_observer_lease WHERE singleton = 1"
            ).fetchone()
        return bool(row["owner"] == owner and int(row["generation"]) == generation and row["expires_at"] and datetime.fromisoformat(row["expires_at"]) > current)

    def release(self, owner: str, generation: int | None = None) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE incident_observer_lease
                   SET owner = NULL, expires_at = NULL
                   WHERE singleton = 1 AND owner = ? AND (? IS NULL OR generation = ?)""",
                (owner, generation, generation),
            )
        return cursor.rowcount == 1
