from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    """Durable state and evidence store backed by the same SQLite database as jobs.

    The store is intentionally schema-light at this stage: campaign documents are
    versioned Pydantic JSON snapshots, while evidence metadata is normalized and
    content is written under a dedicated artifact root with SHA-256 integrity.
    """

    def __init__(self, db_path: str | None = None, artifact_root: str | None = None):
        self.db_path = db_path or os.getenv("XBOW_DB_PATH", "/data/xbow.sqlite3")
        self.artifact_root = Path(artifact_root or os.getenv("XBOW_ARTIFACT_ROOT", "/data/artifacts"))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout=30000")
            yield db
        finally:
            db.close()

    def _init(self) -> None:
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                document TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS campaigns_updated ON campaigns(updated_at DESC)")
            db.execute("""CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                finding_id TEXT,
                kind TEXT NOT NULL,
                media_type TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS artifacts_campaign ON artifacts(campaign_id, created_at)")

    def save_campaign(self, document: dict[str, Any]) -> None:
        required = {"id", "state", "created_at", "updated_at"}
        if not required.issubset(document):
            raise ValueError("campaign document missing required fields")
        encoded = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
        with self.connect() as db:
            db.execute(
                """INSERT INTO campaigns(id,document,state,created_at,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     document=excluded.document,
                     state=excluded.state,
                     updated_at=excluded.updated_at""",
                (document["id"], encoded, str(document["state"]), document["created_at"], document["updated_at"]),
            )

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT document FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        return json.loads(row["document"]) if row else None

    def list_campaigns(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT document FROM campaigns ORDER BY created_at DESC").fetchall()
        return [json.loads(row["document"]) for row in rows]

    def put_artifact(
        self,
        campaign_id: str,
        kind: str,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        finding_id: str | None = None,
    ) -> dict[str, Any]:
        if kind not in {"scanner_stdout", "scanner_stderr", "http_evidence", "screenshot", "validation", "report"}:
            raise ValueError("unsupported artifact kind")
        max_bytes = int(os.getenv("XBOW_MAX_ARTIFACT_BYTES", str(10 * 1024 * 1024)))
        if len(content) > max_bytes:
            raise ValueError("artifact exceeds size limit")
        with self.connect() as db:
            exists = db.execute("SELECT 1 FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if not exists:
            raise KeyError(campaign_id)

        artifact_id = str(uuid4())
        digest = hashlib.sha256(content).hexdigest()
        campaign_dir = self.artifact_root / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)
        path = campaign_dir / f"{artifact_id}.bin"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, path)
        now = utcnow()
        relative = str(path.relative_to(self.artifact_root))
        with self.connect() as db:
            db.execute(
                "INSERT INTO artifacts(id,campaign_id,finding_id,kind,media_type,relative_path,sha256,size_bytes,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (artifact_id, campaign_id, finding_id, kind, media_type, relative, digest, len(content), now),
            )
        return {
            "id": artifact_id,
            "campaign_id": campaign_id,
            "finding_id": finding_id,
            "kind": kind,
            "media_type": media_type,
            "sha256": digest,
            "size_bytes": len(content),
            "created_at": now,
        }

    def list_artifacts(self, campaign_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,campaign_id,finding_id,kind,media_type,sha256,size_bytes,created_at FROM artifacts WHERE campaign_id=? ORDER BY created_at",
                (campaign_id,),
            ).fetchall()
        return [dict(row) for row in rows]
