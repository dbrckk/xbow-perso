from __future__ import annotations

import json
import sqlite3
from typing import Any


class IncidentStoreConflict(RuntimeError):
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

    def write(self, history: list[dict[str, Any]], *, expected_version: int) -> int:
        document = json.dumps(history, sort_keys=True, separators=(",", ":"))
        if len(document.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("incident history document exceeds 2 MiB")
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE operational_incidents
                   SET document = ?, version = version + 1
                   WHERE singleton = 1 AND version = ?""",
                (document, expected_version),
            )
            if cursor.rowcount != 1:
                raise IncidentStoreConflict("incident history changed concurrently")
            row = db.execute(
                "SELECT version FROM operational_incidents WHERE singleton = 1"
            ).fetchone()
        return int(row["version"])
