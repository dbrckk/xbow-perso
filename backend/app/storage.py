from __future__ import annotations

from typing import Any

from . import storage_core as _core


ArtifactIntegrityError = _core.ArtifactIntegrityError
CampaignConflictError = _core.CampaignConflictError
utcnow = _core.utcnow
_max_artifact_bytes = _core._max_artifact_bytes
_max_campaign_document_bytes = _core._max_campaign_document_bytes
_max_observation_bytes = _core._max_observation_bytes
_bounded_identifier = _core._bounded_identifier
_harden_private_path = _core._harden_private_path
_validate_media_type = _core._validate_media_type


class Storage(_core.Storage):
    """Storage core extended with durable PentAGI flow-to-campaign bindings."""

    @staticmethod
    def _ensure_pentagi_flow_bindings(db) -> None:
        db.execute(
            """CREATE TABLE IF NOT EXISTS pentagi_flow_bindings (
                flow_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                policy_fingerprint TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                model_provider TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
            )"""
        )
        db.execute(
            """CREATE INDEX IF NOT EXISTS pentagi_flow_bindings_campaign
               ON pentagi_flow_bindings(campaign_id, created_at)"""
        )

    @staticmethod
    def _normalize_pentagi_flow_binding(binding: dict[str, Any]) -> dict[str, str]:
        required = {
            "flow_id",
            "campaign_id",
            "policy_fingerprint",
            "endpoint",
            "model_provider",
        }
        if not required.issubset(binding):
            raise ValueError("PentAGI flow binding missing required fields")

        flow_id = _bounded_identifier(str(binding["flow_id"]), "flow_id")
        campaign_id = _bounded_identifier(str(binding["campaign_id"]), "campaign_id")
        policy_fingerprint = _bounded_identifier(
            str(binding["policy_fingerprint"]),
            "policy_fingerprint",
            max_length=64,
        )
        if len(policy_fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in policy_fingerprint
        ):
            raise ValueError("policy_fingerprint must be a lowercase SHA-256 hex digest")
        endpoint = _bounded_identifier(
            str(binding["endpoint"]), "pentagi_endpoint", max_length=2048
        )
        model_provider = _bounded_identifier(
            str(binding["model_provider"]), "model_provider", max_length=64
        )
        return {
            "flow_id": flow_id,
            "campaign_id": campaign_id,
            "policy_fingerprint": policy_fingerprint,
            "endpoint": endpoint,
            "model_provider": model_provider,
        }

    def put_pentagi_flow_binding(self, binding: dict[str, Any]) -> dict[str, str]:
        requested = self._normalize_pentagi_flow_binding(binding)
        with self.connect() as db:
            self._ensure_pentagi_flow_bindings(db)
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM campaigns WHERE id=?", (requested["campaign_id"],)
            ).fetchone():
                db.execute("ROLLBACK")
                raise KeyError(requested["campaign_id"])

            existing = db.execute(
                """SELECT flow_id,campaign_id,policy_fingerprint,endpoint,model_provider,created_at
                   FROM pentagi_flow_bindings WHERE flow_id=?""",
                (requested["flow_id"],),
            ).fetchone()
            if existing:
                record = dict(existing)
                comparable = {
                    key: record[key]
                    for key in (
                        "flow_id",
                        "campaign_id",
                        "policy_fingerprint",
                        "endpoint",
                        "model_provider",
                    )
                }
                if comparable != requested:
                    db.execute("ROLLBACK")
                    raise ValueError("PentAGI flow binding conflict")
                db.execute("COMMIT")
                return record

            created_at = utcnow()
            db.execute(
                """INSERT INTO pentagi_flow_bindings(
                       flow_id,campaign_id,policy_fingerprint,endpoint,model_provider,created_at
                   ) VALUES(?,?,?,?,?,?)""",
                (
                    requested["flow_id"],
                    requested["campaign_id"],
                    requested["policy_fingerprint"],
                    requested["endpoint"],
                    requested["model_provider"],
                    created_at,
                ),
            )
            db.execute("COMMIT")
        return {**requested, "created_at": created_at}

    def get_pentagi_flow_binding(self, flow_id: str) -> dict[str, str] | None:
        flow_id = _bounded_identifier(flow_id, "flow_id")
        with self.connect() as db:
            self._ensure_pentagi_flow_bindings(db)
            row = db.execute(
                """SELECT flow_id,campaign_id,policy_fingerprint,endpoint,model_provider,created_at
                   FROM pentagi_flow_bindings WHERE flow_id=?""",
                (flow_id,),
            ).fetchone()
        return dict(row) if row else None
