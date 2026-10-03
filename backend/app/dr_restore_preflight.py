from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from .dr_manifest import DisasterRecoveryError, verify_backup_manifest


_SECRET_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_MAX_VAULT_BYTES = 1024 * 1024


def _safe_file(path_value: str, label: str) -> Path:
    path = Path(path_value)
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("unsafe file")
        stat = path.stat()
    except OSError as exc:
        raise DisasterRecoveryError(f"{label} backup file is unavailable") from exc
    if stat.st_size <= 0:
        raise DisasterRecoveryError(f"{label} backup file is empty")
    return path


def _inspect_postgres_dump(path_value: str) -> dict[str, Any]:
    path = _safe_file(path_value, "postgres")
    try:
        with path.open("rb") as handle:
            prefix = handle.read(8192)
    except OSError as exc:
        raise DisasterRecoveryError("postgres backup file could not be read") from exc

    if prefix.startswith(b"PGDMP"):
        dump_format = "custom"
    elif len(prefix) >= 262 and prefix[257:262] == b"ustar":
        dump_format = "tar"
    elif b"PostgreSQL database dump" in prefix:
        dump_format = "plain_sql"
    else:
        dump_format = "unrecognized"

    return {
        "recognized": dump_format != "unrecognized",
        "format": dump_format,
    }


def _inspect_redis_snapshot(path_value: str) -> dict[str, Any]:
    path = _safe_file(path_value, "redis")
    try:
        with path.open("rb") as handle:
            header = handle.read(9)
    except OSError as exc:
        raise DisasterRecoveryError("redis backup file could not be read") from exc

    valid = (
        len(header) == 9
        and header.startswith(b"REDIS")
        and header[5:9].isdigit()
    )
    return {
        "recognized": valid,
        "format": "rdb" if valid else "unrecognized",
        "rdb_version": int(header[5:9]) if valid else None,
    }


def _decode_vault_field(value: Any) -> bytes | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return base64.b64decode(value.encode("ascii"), altchars=b"-_", validate=True)
    except (ValueError, UnicodeEncodeError):
        return None


def _inspect_vault_copy(path_value: str) -> dict[str, Any]:
    path = _safe_file(path_value, "vault")
    try:
        if path.stat().st_size > _MAX_VAULT_BYTES:
            raise OSError("vault too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DisasterRecoveryError("vault backup structure is invalid") from exc

    if payload.get("version") != 1 or not isinstance(payload.get("secrets"), dict):
        return {
            "recognized": False,
            "format": "unrecognized",
            "secret_count": 0,
        }

    secrets = payload["secrets"]
    valid = True
    for name, record in secrets.items():
        if not isinstance(name, str) or not _SECRET_NAME_RE.fullmatch(name):
            valid = False
            break
        if not isinstance(record, dict):
            valid = False
            break
        nonce = _decode_vault_field(record.get("nonce"))
        ciphertext = _decode_vault_field(record.get("ciphertext"))
        if nonce is None or len(nonce) != 12:
            valid = False
            break
        if ciphertext is None or not 16 <= len(ciphertext) <= 16400:
            valid = False
            break

    return {
        "recognized": valid,
        "format": "xbow_vault_v1" if valid else "unrecognized",
        "secret_count": len(secrets) if valid else 0,
    }


def assess_restore_preflight(
    manifest_path: str,
    *,
    postgres_dump: str,
    redis_snapshot: str,
    vault_copy: str,
) -> dict[str, Any]:
    """Perform a non-destructive structural preflight for a DR backup set.

    This verifies integrity and recognizable backup structure only. It never
    restores PostgreSQL, loads Redis, decrypts vault secrets, or modifies data.
    """
    verification = verify_backup_manifest(
        manifest_path,
        postgres_dump=postgres_dump,
        redis_snapshot=redis_snapshot,
        vault_copy=vault_copy,
    )

    postgres = _inspect_postgres_dump(postgres_dump)
    redis = _inspect_redis_snapshot(redis_snapshot)
    vault = _inspect_vault_copy(vault_copy)

    blockers: list[str] = []
    warnings: list[str] = []
    if verification.get("valid") is not True:
        blockers.append("backup_integrity_invalid")
    if postgres["recognized"] is not True:
        blockers.append("postgres_dump_format_unrecognized")
    if redis["recognized"] is not True:
        blockers.append("redis_snapshot_format_unrecognized")
    if vault["recognized"] is not True:
        blockers.append("vault_backup_format_unrecognized")

    signature_state = verification.get("manifest_signature_valid")
    if signature_state is None:
        warnings.append("manifest_unsigned_legacy")
    if vault.get("secret_count") == 0 and vault["recognized"] is True:
        warnings.append("vault_contains_no_secrets")

    return {
        "restore_preflight_ready": not blockers,
        "integrity_valid": verification.get("valid") is True,
        "manifest_signature_valid": signature_state,
        "artifacts": {
            "postgres": postgres,
            "redis": redis,
            "vault": vault,
        },
        "blockers": blockers,
        "warnings": warnings,
        "non_destructive": True,
        "actual_restore_tested": False,
        "automatic_restore": False,
        "contains_backup_contents": False,
        "contains_secrets": False,
        "contains_secret_names": False,
    }
