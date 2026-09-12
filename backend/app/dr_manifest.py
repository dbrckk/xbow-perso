from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class DisasterRecoveryError(RuntimeError):
    pass


def _safe_backup_file(path_value: str, label: str) -> Path:
    path = Path(path_value)
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("not a regular non-symlink file")
        stat = path.stat()
    except OSError as exc:
        raise DisasterRecoveryError(f"{label} backup file is unavailable") from exc
    if stat.st_size <= 0:
        raise DisasterRecoveryError(f"{label} backup file is empty")
    if stat.st_size > 50 * 1024 * 1024 * 1024:
        raise DisasterRecoveryError(f"{label} backup file exceeds 50 GiB safety limit")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DisasterRecoveryError("backup file could not be read") from exc
    return digest.hexdigest()


def build_backup_manifest(
    *,
    postgres_dump: str,
    redis_snapshot: str,
    vault_copy: str,
) -> dict[str, Any]:
    entries = []
    for kind, value in (
        ("postgres", postgres_dump),
        ("redis", redis_snapshot),
        ("vault", vault_copy),
    ):
        path = _safe_backup_file(value, kind)
        stat = path.stat()
        entries.append(
            {
                "kind": kind,
                "filename": path.name,
                "size_bytes": int(stat.st_size),
                "sha256": _sha256(path),
            }
        )
    return {
        "version": 1,
        "artifacts": entries,
        "contains_secrets": False,
        "contains_backup_contents": False,
    }


def write_backup_manifest(manifest: dict[str, Any], destination: str) -> None:
    path = Path(destination)
    if path.is_symlink():
        raise DisasterRecoveryError("manifest path must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    encoded = json.dumps(manifest, sort_keys=True, indent=2)
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            os.chmod(tmp, 0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise DisasterRecoveryError("manifest write failed") from exc


def verify_backup_manifest(
    manifest_path: str,
    *,
    postgres_dump: str,
    redis_snapshot: str,
    vault_copy: str,
) -> dict[str, Any]:
    path = Path(manifest_path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise OSError("unsafe manifest")
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DisasterRecoveryError("manifest is invalid") from exc

    if manifest.get("version") != 1 or not isinstance(manifest.get("artifacts"), list):
        raise DisasterRecoveryError("unsupported manifest format")

    current = build_backup_manifest(
        postgres_dump=postgres_dump,
        redis_snapshot=redis_snapshot,
        vault_copy=vault_copy,
    )
    expected = {
        str(item.get("kind")): item
        for item in manifest["artifacts"]
        if isinstance(item, dict)
    }
    actual = {item["kind"]: item for item in current["artifacts"]}

    results = {}
    valid = True
    for kind in ("postgres", "redis", "vault"):
        left = expected.get(kind)
        right = actual.get(kind)
        if left is not None:
            size_value = left.get("size_bytes")
            if not isinstance(size_value, int) or isinstance(size_value, bool) or size_value < 0:
                raise DisasterRecoveryError("manifest artifact size is invalid")
            if not isinstance(left.get("filename"), str) or not isinstance(left.get("sha256"), str):
                raise DisasterRecoveryError("manifest artifact metadata is invalid")
        match = bool(
            left
            and right
            and left.get("filename") == right.get("filename")
            and left.get("size_bytes") == right.get("size_bytes")
            and left.get("sha256") == right.get("sha256")
        )
        results[kind] = {"valid": match}
        valid = valid and match

    return {
        "valid": valid,
        "artifacts": results,
        "contains_secrets": False,
        "contains_backup_contents": False,
    }
