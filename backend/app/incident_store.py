from __future__ import annotations

import json
import sqlite3
from typing import Any


class IncidentStoreConflict(RuntimeError):
    pass


class IncidentFenceConflict(IncidentStoreConflict):
    pass


class IncidentStore:
    """Transactional SQLite persistence for redacted operational incident history."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init()

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _init(self) -> None:
        with self._connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS operational_incidents (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    document TEXT NOT NULL,
                    version INTEGER NOT NULL
                )"""
            )
            db.execute(
                "INSERT OR IGNORE INTO operational_incidents(singleton, document, version) VALUES(1, '[]', 1)"
            )

    def read(self) -> tuple[list[dict[str, Any]], int]:
        with self._connect() as db:
            row = db.execute(
                "SELECT document, version FROM operational_incidents WHERE singleton = 1"
            ).fetchone()
        return json.loads(row["document"]), int(row["version"])

    def write(
        self,
        history: list[dict[str, Any]],
        *,
        expected_version: int,
        fence_owner: str | None = None,
        fence_generation: int | None = None,
    ) -> int:
        document = json.dumps(history, sort_keys=True, separators=(",", ":"))
        if len(document.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("incident history document exceeds 2 MiB")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if fence_owner is not None or fence_generation is not None:
                if not fence_owner or fence_generation is None:
                    db.execute("ROLLBACK")
                    raise IncidentFenceConflict("incomplete incident observer fence")
                lease = db.execute(
                    "SELECT owner, generation, expires_at FROM incident_observer_lease WHERE singleton = 1"
                ).fetchone()
                if lease is None:
                    db.execute("ROLLBACK")
                    raise IncidentFenceConflict("incident observer lease unavailable")
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                expires = datetime.fromisoformat(lease["expires_at"]) if lease["expires_at"] else None
                if lease["owner"] != fence_owner or int(lease["generation"]) != fence_generation or expires is None or expires <= now:
                    db.execute("ROLLBACK")
                    raise IncidentFenceConflict("incident observer leadership fence is stale")
            cursor = db.execute(
                """UPDATE operational_incidents
                   SET document = ?, version = version + 1
                   WHERE singleton = 1 AND version = ?""",
                (document, expected_version),
            )
            if cursor.rowcount != 1:
                db.execute("ROLLBACK")
                raise IncidentStoreConflict("incident history changed concurrently")
            row = db.execute(
                "SELECT version FROM operational_incidents WHERE singleton = 1"
            ).fetchone()
            db.execute("COMMIT")
        return int(row["version"])
