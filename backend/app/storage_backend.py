from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from .storage import Storage


@runtime_checkable
class StorageBackend(Protocol):
    artifact_root: object

    def save_campaign(self, document: dict, *, expected_version: int | None = None) -> int: ...
    def get_campaign_record(self, campaign_id: str): ...
    def get_campaign(self, campaign_id: str): ...
    def list_campaigns(self) -> list[dict]: ...
    def put_observation(self, campaign_id: str, observation: dict) -> dict: ...
    def list_observations(self, campaign_id: str) -> list[dict]: ...
    def put_hypothesis_snapshot(self, campaign_id: str, graph_fingerprint: str, hypotheses: list[dict]) -> dict: ...
    def list_hypothesis_snapshots(self, campaign_id: str, *, limit: int = 50) -> list[dict]: ...
    def put_advisory_focus_snapshot(self, campaign_id: str, fingerprint: str, advisory: dict) -> dict: ...
    def list_advisory_focus_snapshots(self, campaign_id: str, *, limit: int = 50) -> list[dict]: ...
    def put_artifact(self, campaign_id: str, kind: str, content: bytes, **kwargs) -> dict: ...
    def list_artifacts(self, campaign_id: str) -> list[dict]: ...
    def read_artifact(self, campaign_id: str, artifact_id: str): ...
    def get_artifact(self, campaign_id: str, artifact_id: str): ...
    def has_artifact(self, campaign_id: str, **kwargs) -> bool: ...


def storage_backend_name() -> str:
    value = os.getenv("XBOW_STORAGE_BACKEND", "sqlite").strip().lower()
    aliases = {
        "sqlite3": "sqlite",
        "postgres": "postgresql",
        "postgresql": "postgresql",
    }
    value = aliases.get(value, value)
    if value not in {"sqlite", "postgresql"}:
        raise ValueError("XBOW_STORAGE_BACKEND must be sqlite or postgresql")
    return value


def create_storage() -> StorageBackend:
    backend = storage_backend_name()
    if backend == "sqlite":
        return Storage()
    raise RuntimeError(
        "PostgreSQL storage backend is selected but not installed; "
        "use XBOW_STORAGE_BACKEND=sqlite until the PostgreSQL adapter is configured"
    )
