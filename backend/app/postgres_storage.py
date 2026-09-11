from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from .storage import Storage, _harden_private_path


class _PostgresCompatConnection:
    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _sql(statement: str) -> str:
        normalized = statement.strip()
        if normalized.upper() == "BEGIN IMMEDIATE":
            return "BEGIN"
        return statement.replace("?", "%s")

    def execute(self, statement: str, params=()):
        return self._connection.execute(self._sql(statement), params)


class PostgresStorage(Storage):
    """PostgreSQL-backed campaign metadata with the same artifact semantics as Storage."""

    def __init__(
        self,
        database_url: str | None = None,
        artifact_root: str | None = None,
    ):
        self.database_url = (
            database_url
            or os.getenv("XBOW_DATABASE_URL")
            or os.getenv("DATABASE_URL")
            or ""
        ).strip()
        if not self.database_url:
            raise ValueError("XBOW_DATABASE_URL is required for PostgreSQL storage")
        parsed = urlparse(self.database_url)
        if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname:
            raise ValueError("XBOW_DATABASE_URL must be a PostgreSQL URL")

        self.artifact_root = Path(
            artifact_root or os.getenv("XBOW_ARTIFACT_ROOT", "/data/artifacts")
        )
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        _harden_private_path(self.artifact_root, 0o700)
        self._init()

    @contextmanager
    def connect(self):
        connection = psycopg.connect(
            self.database_url,
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=10,
        )
        try:
            yield _PostgresCompatConnection(connection)
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError(str(exc)) from exc
        finally:
            connection.close()

    def _init(self) -> None:
        with self.connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                )"""
            )
            db.execute(
                "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_updated ON campaigns(updated_at DESC)"
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    finding_id TEXT,
                    kind TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    idempotency_key TEXT
                )"""
            )
            db.execute(
                "ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS idempotency_key TEXT"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS artifacts_campaign ON artifacts(campaign_id, created_at)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS artifacts_finding ON artifacts(campaign_id, finding_id, kind)"
            )
            db.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS artifacts_idempotency
                   ON artifacts(campaign_id, idempotency_key)
                   WHERE idempotency_key IS NOT NULL"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS observations (
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    parent_ids TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(campaign_id, id)
                )"""
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS observations_campaign_kind
                   ON observations(campaign_id, kind, created_at)"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS hypothesis_snapshots (
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    graph_fingerprint TEXT NOT NULL,
                    document TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(campaign_id, graph_fingerprint)
                )"""
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS hypothesis_snapshots_campaign_created
                   ON hypothesis_snapshots(campaign_id, created_at DESC)"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS advisory_focus_snapshots (
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    fingerprint TEXT NOT NULL,
                    document TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(campaign_id, fingerprint)
                )"""
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS advisory_focus_snapshots_campaign_created
                   ON advisory_focus_snapshots(campaign_id, created_at DESC)"""
            )
