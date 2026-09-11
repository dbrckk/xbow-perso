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


class ArtifactIntegrityError(RuntimeError):
    pass


class CampaignConflictError(RuntimeError):
    pass


def _max_artifact_bytes() -> int:
    raw = os.getenv("XBOW_MAX_ARTIFACT_BYTES", str(10 * 1024 * 1024))
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError("XBOW_MAX_ARTIFACT_BYTES must be an integer") from exc
    if not 1024 <= limit <= 100 * 1024 * 1024:
        raise ValueError("XBOW_MAX_ARTIFACT_BYTES must be between 1 KiB and 100 MiB")
    return limit


def _bounded_identifier(value: str, name: str, *, max_length: int = 200) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} required")
    if len(normalized) > max_length:
        raise ValueError(f"{name} too long")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in normalized):
        raise ValueError(f"{name} contains invalid characters")
    return normalized


def _validate_media_type(media_type: str) -> str:
    value = media_type.strip()
    if not value or len(value) > 120 or "/" not in value:
        raise ValueError("invalid artifact media type")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("invalid artifact media type")
    return value


class Storage:
    """Durable campaign state plus content-addressed evidence metadata."""

    ALLOWED_ARTIFACT_KINDS = {
        "scanner_stdout",
        "scanner_stderr",
        "http_evidence",
        "screenshot",
        "validation",
        "report",
    }
    ALLOWED_OBSERVATION_KINDS = {
        "asset",
        "endpoint",
        "technology",
        "finding",
        "evidence",
        "validation",
    }

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
            db.execute("PRAGMA foreign_keys=ON")
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
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )""")
            campaign_columns = {row["name"] for row in db.execute("PRAGMA table_info(campaigns)").fetchall()}
            if "version" not in campaign_columns:
                db.execute("ALTER TABLE campaigns ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
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
                idempotency_key TEXT,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
            )""")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(artifacts)").fetchall()}
            if "idempotency_key" not in columns:
                db.execute("ALTER TABLE artifacts ADD COLUMN idempotency_key TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS artifacts_campaign ON artifacts(campaign_id, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS artifacts_finding ON artifacts(campaign_id, finding_id, kind)")
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS artifacts_idempotency ON artifacts(campaign_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
            )
            db.execute("""CREATE TABLE IF NOT EXISTS observations (
                campaign_id TEXT NOT NULL,
                id TEXT NOT NULL,
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL,
                parent_ids TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(campaign_id, id),
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS observations_campaign_kind ON observations(campaign_id, kind, created_at)")

    def save_campaign(self, document: dict[str, Any], *, expected_version: int | None = None) -> int:
        """Persist a campaign and optionally reject stale snapshot writes.

        Callers that perform read-modify-write cycles can pass the version returned
        by get_campaign_record(). A mismatch fails instead of silently overwriting
        a newer campaign snapshot.
        """
        required = {"id", "state", "created_at", "updated_at"}
        if not required.issubset(document):
            raise ValueError("campaign document missing required fields")
        document = dict(document)
        document["id"] = _bounded_identifier(str(document["id"]), "campaign_id")
        encoded = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT version FROM campaigns WHERE id=?", (document["id"],)).fetchone()
            if current is None:
                if expected_version not in (None, 0):
                    db.execute("ROLLBACK")
                    raise CampaignConflictError("campaign version conflict")
                db.execute(
                    "INSERT INTO campaigns(id,document,state,created_at,updated_at,version) VALUES(?,?,?,?,?,1)",
                    (document["id"], encoded, str(document["state"]), document["created_at"], document["updated_at"]),
                )
                db.execute("COMMIT")
                return 1

            current_version = int(current["version"])
            if expected_version is not None and expected_version != current_version:
                db.execute("ROLLBACK")
                raise CampaignConflictError("campaign version conflict")
            next_version = current_version + 1
            db.execute(
                """UPDATE campaigns
                   SET document=?, state=?, updated_at=?, version=?
                   WHERE id=? AND version=?""",
                (encoded, str(document["state"]), document["updated_at"], next_version, document["id"], current_version),
            )
            db.execute("COMMIT")
            return next_version

    def get_campaign_record(self, campaign_id: str) -> tuple[dict[str, Any], int] | None:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        with self.connect() as db:
            row = db.execute("SELECT document,version FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        return (json.loads(row["document"]), int(row["version"])) if row else None

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        record = self.get_campaign_record(campaign_id)
        return record[0] if record else None

    def list_campaigns(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT document FROM campaigns ORDER BY created_at DESC").fetchall()
        return [json.loads(row["document"]) for row in rows]

    def put_observation(self, campaign_id: str, observation: dict[str, Any]) -> dict[str, Any]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        required = {"id", "kind", "value", "source"}
        if not required.issubset(observation):
            raise ValueError("observation missing required fields")
        kind = str(observation["kind"])
        if kind not in self.ALLOWED_OBSERVATION_KINDS:
            raise ValueError("unsupported observation kind")
        parent_ids = tuple(str(item) for item in observation.get("parent_ids", ()))
        metadata = observation.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("observation metadata must be an object")
        record = {
            "campaign_id": campaign_id,
            "id": _bounded_identifier(str(observation["id"]), "observation_id"),
            "kind": kind,
            "value": str(observation["value"]),
            "source": str(observation["source"]),
            "parent_ids": parent_ids,
            "metadata": metadata,
            "created_at": str(observation.get("created_at") or utcnow()),
        }
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM campaigns WHERE id=?", (campaign_id,)).fetchone():
                db.execute("ROLLBACK")
                raise KeyError(campaign_id)
            if parent_ids:
                placeholders = ",".join("?" for _ in parent_ids)
                rows = db.execute(
                    f"SELECT id FROM observations WHERE campaign_id=? AND id IN ({placeholders})",
                    (campaign_id, *parent_ids),
                ).fetchall()
                if {row["id"] for row in rows} != set(parent_ids):
                    db.execute("ROLLBACK")
                    raise ValueError("observation references unknown parent")
            existing = db.execute(
                "SELECT kind,value,source,parent_ids,metadata,created_at FROM observations WHERE campaign_id=? AND id=?",
                (campaign_id, record["id"]),
            ).fetchone()
            if existing:
                comparable = {
                    "kind": existing["kind"],
                    "value": existing["value"],
                    "source": existing["source"],
                    "parent_ids": tuple(json.loads(existing["parent_ids"])),
                    "metadata": json.loads(existing["metadata"]),
                }
                requested = {key: record[key] for key in ("kind", "value", "source", "parent_ids", "metadata")}
                if comparable != requested:
                    db.execute("ROLLBACK")
                    raise ValueError("observation id reused with different content")
                db.execute("COMMIT")
                return {**record, "created_at": existing["created_at"]}
            db.execute(
                """INSERT INTO observations(campaign_id,id,kind,value,source,parent_ids,metadata,created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    campaign_id,
                    record["id"],
                    record["kind"],
                    record["value"],
                    record["source"],
                    json.dumps(parent_ids, separators=(",", ":")),
                    json.dumps(metadata, separators=(",", ":"), ensure_ascii=False),
                    record["created_at"],
                ),
            )
            db.execute("COMMIT")
        return record

    def list_observations(self, campaign_id: str) -> list[dict[str, Any]]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        with self.connect() as db:
            rows = db.execute(
                "SELECT campaign_id,id,kind,value,source,parent_ids,metadata,created_at FROM observations WHERE campaign_id=? ORDER BY created_at,id",
                (campaign_id,),
            ).fetchall()
        return [
            {
                "campaign_id": row["campaign_id"],
                "id": row["id"],
                "kind": row["kind"],
                "value": row["value"],
                "source": row["source"],
                "parent_ids": tuple(json.loads(row["parent_ids"])),
                "metadata": json.loads(row["metadata"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _safe_campaign_artifact_dir(self, campaign_id: str) -> Path:
        root = self.artifact_root.resolve()
        candidate = self.artifact_root / campaign_id
        if candidate.is_symlink():
            raise ArtifactIntegrityError("campaign artifact directory must not be a symlink")
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ArtifactIntegrityError("campaign artifact path escaped storage root") from exc
        resolved.mkdir(parents=True, exist_ok=True)
        final = resolved.resolve()
        try:
            final.relative_to(root)
        except ValueError as exc:
            raise ArtifactIntegrityError("campaign artifact path escaped storage root") from exc
        return final

    def put_artifact(
        self,
        campaign_id: str,
        kind: str,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        finding_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        if finding_id is not None:
            finding_id = _bounded_identifier(finding_id, "finding_id")
        if kind not in self.ALLOWED_ARTIFACT_KINDS:
            raise ValueError("unsupported artifact kind")
        if idempotency_key is not None:
            idempotency_key = idempotency_key.strip()
            if not idempotency_key:
                raise ValueError("idempotency_key must not be blank")
            if len(idempotency_key) > 200:
                raise ValueError("idempotency_key too long")
            if any(ord(ch) < 33 or ord(ch) == 127 for ch in idempotency_key):
                raise ValueError("idempotency_key contains invalid characters")
        max_bytes = _max_artifact_bytes()
        if len(content) > max_bytes:
            raise ValueError("artifact exceeds size limit")
        media_type = _validate_media_type(media_type)
        digest = hashlib.sha256(content).hexdigest()

        with self.connect() as db:
            exists = db.execute("SELECT 1 FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if not exists:
                raise KeyError(campaign_id)
            if idempotency_key is not None:
                existing = db.execute(
                    """SELECT id,campaign_id,finding_id,kind,media_type,sha256,size_bytes,created_at,idempotency_key
                       FROM artifacts WHERE campaign_id=? AND idempotency_key=?""",
                    (campaign_id, idempotency_key),
                ).fetchone()
                if existing:
                    if existing["sha256"] != digest or existing["kind"] != kind:
                        raise ArtifactIntegrityError("idempotency key reused with different artifact content")
                    return dict(existing)

        artifact_id = str(uuid4())
        root = self.artifact_root.resolve()
        campaign_dir = self._safe_campaign_artifact_dir(campaign_id)
        path = campaign_dir / f"{artifact_id}.bin"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(content)
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        now = utcnow()
        relative = str(path.relative_to(root))
        try:
            with self.connect() as db:
                db.execute(
                    """INSERT INTO artifacts(id,campaign_id,finding_id,kind,media_type,relative_path,sha256,size_bytes,created_at,idempotency_key)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (artifact_id, campaign_id, finding_id, kind, media_type, relative, digest, len(content), now, idempotency_key),
                )
        except sqlite3.IntegrityError:
            path.unlink(missing_ok=True)
            if idempotency_key is None:
                raise
            with self.connect() as db:
                existing = db.execute(
                    """SELECT id,campaign_id,finding_id,kind,media_type,sha256,size_bytes,created_at,idempotency_key
                       FROM artifacts WHERE campaign_id=? AND idempotency_key=?""",
                    (campaign_id, idempotency_key),
                ).fetchone()
            if not existing or existing["sha256"] != digest or existing["kind"] != kind:
                raise ArtifactIntegrityError("idempotent artifact write conflicted")
            return dict(existing)
        except sqlite3.Error:
            path.unlink(missing_ok=True)
            raise
        return {
            "id": artifact_id,
            "campaign_id": campaign_id,
            "finding_id": finding_id,
            "kind": kind,
            "media_type": media_type,
            "sha256": digest,
            "size_bytes": len(content),
            "created_at": now,
            "idempotency_key": idempotency_key,
        }

    def list_artifacts(self, campaign_id: str) -> list[dict[str, Any]]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,campaign_id,finding_id,kind,media_type,sha256,size_bytes,created_at,idempotency_key FROM artifacts WHERE campaign_id=? ORDER BY created_at",
                (campaign_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_artifact(self, campaign_id: str, artifact_id: str) -> dict[str, Any] | None:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        artifact_id = _bounded_identifier(artifact_id, "artifact_id")
        with self.connect() as db:
            row = db.execute(
                """SELECT id,campaign_id,finding_id,kind,media_type,relative_path,sha256,size_bytes,created_at,idempotency_key
                   FROM artifacts WHERE id=? AND campaign_id=?""",
                (artifact_id, campaign_id),
            ).fetchone()
        return dict(row) if row else None

    def has_artifact(self, campaign_id: str, *, finding_id: str | None = None, kind: str | None = None) -> bool:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        clauses = ["campaign_id=?"]
        params: list[Any] = [campaign_id]
        if finding_id is not None:
            finding_id = _bounded_identifier(finding_id, "finding_id")
            clauses.append("finding_id=?")
            params.append(finding_id)
        if kind is not None:
            if kind not in self.ALLOWED_ARTIFACT_KINDS:
                raise ValueError("unsupported artifact kind")
            clauses.append("kind=?")
            params.append(kind)
        with self.connect() as db:
            row = db.execute(f"SELECT 1 FROM artifacts WHERE {' AND '.join(clauses)} LIMIT 1", params).fetchone()
        return bool(row)

    def read_artifact(self, campaign_id: str, artifact_id: str) -> tuple[dict[str, Any], bytes]:
        metadata = self.get_artifact(campaign_id, artifact_id)
        if not metadata:
            raise KeyError(artifact_id)

        root = self.artifact_root.resolve()
        path = (self.artifact_root / metadata["relative_path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ArtifactIntegrityError("artifact path escaped storage root") from exc
        if not path.is_file():
            raise ArtifactIntegrityError("artifact content is missing")

        content = path.read_bytes()
        if len(content) != metadata["size_bytes"]:
            raise ArtifactIntegrityError("artifact size mismatch")
        digest = hashlib.sha256(content).hexdigest()
        if digest != metadata["sha256"]:
            raise ArtifactIntegrityError("artifact sha256 mismatch")
        public_metadata = {key: value for key, value in metadata.items() if key != "relative_path"}
        return public_metadata, content
