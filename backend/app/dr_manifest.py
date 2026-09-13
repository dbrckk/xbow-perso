from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from .secret_vault import SecretVaultError, resolve_secret


_LEGACY_SIGNATURE_FIELDS = {
    "manifest_signature",
    "manifest_signature_alg",
    "integrity_mode",
}
_V2_SIGNATURE_FIELDS = {"manifest_signature", "manifest_signature_alg"}
_V2_INTEGRITY_MODE = "sha256-artifacts+hmac-sha256-manifest"


class DisasterRecoveryError(RuntimeError):
    pass


def _canonical_manifest(manifest: dict[str, Any]) -> bytes:
    version = manifest.get("version")
    excluded = (
        _LEGACY_SIGNATURE_FIELDS
        if version == 1
        else _V2_SIGNATURE_FIELDS
    )
    payload = {
        key: value
        for key, value in manifest.items()
        if key not in excluded
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _seal_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(manifest)
    try:
        secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
    except SecretVaultError as exc:
        raise DisasterRecoveryError("DR manifest signing key is unavailable") from exc

    if not secret:
        sealed["manifest_signature_alg"] = None
        sealed["manifest_signature"] = None
        sealed["integrity_mode"] = "sha256-artifacts"
        return sealed

    # Version 2 makes authenticated manifests unambiguously authenticated.
    # A v2 manifest cannot be downgraded to an unsigned legacy manifest merely
    # by deleting signature metadata.
    sealed["version"] = 2
    sealed["manifest_signature_alg"] = "hmac-sha256"
    sealed["integrity_mode"] = _V2_INTEGRITY_MODE
    canonical = _canonical_manifest(sealed)
    sealed["manifest_signature"] = hmac.new(
        secret.encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()
    return sealed


def _verification_secret() -> str:
    try:
        secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
    except SecretVaultError as exc:
        raise DisasterRecoveryError("DR manifest verification key is unavailable") from exc
    if not secret:
        raise DisasterRecoveryError("DR manifest verification key is unavailable")
    return secret


def _verify_manifest_signature(manifest: dict[str, Any]) -> bool | None:
    version = manifest.get("version")
    signature = manifest.get("manifest_signature")
    algorithm = manifest.get("manifest_signature_alg")
    integrity_mode = manifest.get("integrity_mode")

    if version == 2:
        if (
            algorithm != "hmac-sha256"
            or integrity_mode != _V2_INTEGRITY_MODE
            or not isinstance(signature, str)
            or len(signature) != 64
        ):
            raise DisasterRecoveryError(
                "signed DR manifest authentication metadata is missing or invalid"
            )
        try:
            int(signature, 16)
        except ValueError as exc:
            raise DisasterRecoveryError(
                "signed DR manifest authentication metadata is missing or invalid"
            ) from exc
    elif version == 1:
        # Legacy unsigned v1 manifests remain readable. Legacy signed v1
        # manifests also remain verifiable using their original canonical form.
        if signature is None:
            if algorithm not in (None, ""):
                raise DisasterRecoveryError(
                    "legacy DR manifest signature metadata is inconsistent"
                )
            if integrity_mode not in (None, "", "sha256-artifacts"):
                raise DisasterRecoveryError(
                    "legacy DR manifest signature metadata is inconsistent"
                )
            return None
        if algorithm != "hmac-sha256":
            raise DisasterRecoveryError("unsupported DR manifest signature algorithm")
        if not isinstance(signature, str):
            raise DisasterRecoveryError("legacy DR manifest signature is invalid")
    else:
        raise DisasterRecoveryError("unsupported manifest format")

    secret = _verification_secret()
    expected = hmac.new(
        secret.encode("utf-8"),
        _canonical_manifest(manifest),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


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
    sealed = _seal_manifest(manifest)
    encoded = json.dumps(sealed, sort_keys=True, indent=2)
    owns_tmp = False
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            owns_tmp = True
            os.chmod(tmp, 0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        owns_tmp = False
        os.chmod(path, 0o600)
    except OSError as exc:
        # An exclusive-open collision belongs to another writer. Only clean
        # up a temporary file successfully created by this invocation.
        if owns_tmp:
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

    if (
        manifest.get("version") not in (1, 2)
        or not isinstance(manifest.get("artifacts"), list)
    ):
        raise DisasterRecoveryError("unsupported manifest format")

    signature_valid = _verify_manifest_signature(manifest)
    if signature_valid is False:
        return {
            "valid": False,
            "artifacts": {},
            "manifest_signature_valid": False,
            "contains_secrets": False,
            "contains_backup_contents": False,
        }

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
        "manifest_signature_valid": signature_valid,
        "contains_secrets": False,
        "contains_backup_contents": False,
    }
