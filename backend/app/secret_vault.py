from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretVaultError(RuntimeError):
    pass


def _decode_master_key(value: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(value.encode("ascii"))
    except Exception as exc:
        raise SecretVaultError("vault master key is invalid") from exc
    if len(key) != 32:
        raise SecretVaultError("vault master key must decode to 32 bytes")
    return key


def load_master_key() -> bytes:
    inline = os.getenv("XBOW_VAULT_MASTER_KEY", "").strip()
    key_file = os.getenv("XBOW_VAULT_MASTER_KEY_FILE", "").strip()
    if inline and key_file:
        raise SecretVaultError("vault master key has conflicting sources")
    if key_file:
        path = Path(key_file)
        try:
            if path.is_symlink() or not path.is_file():
                raise OSError("not a regular non-symlink file")
            stat = path.stat()
            if stat.st_mode & 0o077:
                raise OSError("master key file permissions are too broad")
            if stat.st_size > 256:
                raise OSError("master key file too large")
            inline = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise SecretVaultError("vault master key file is unavailable") from exc
    if not inline:
        raise SecretVaultError("vault master key is not configured")
    return _decode_master_key(inline)


def _vault_path() -> Path:
    raw = os.getenv("XBOW_VAULT_PATH", "/data/secrets.vault.json").strip()
    path = Path(raw)
    if path.is_symlink():
        raise SecretVaultError("vault path must not be a symlink")
    return path


def _load_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "secrets": {}}
    try:
        stat = path.stat()
        if (
            not path.is_file()
            or stat.st_size > 1_048_576
            or stat.st_mode & 0o077
        ):
            raise OSError("unsafe vault file")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SecretVaultError("vault file is invalid") from exc
    if data.get("version") != 1 or not isinstance(data.get("secrets"), dict):
        raise SecretVaultError("unsupported vault format")
    return data


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
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
        raise SecretVaultError("vault write failed") from exc


def set_secret(name: str, value: str) -> None:
    if not name or len(name) > 128 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for ch in name):
        raise SecretVaultError("secret name is invalid")
    if not value or len(value.encode("utf-8")) > 16384:
        raise SecretVaultError("secret value is invalid")
    key = load_master_key()
    path = _vault_path()
    doc = _load_document(path)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, value.encode("utf-8"), name.encode("utf-8"))
    doc["secrets"][name] = {
        "nonce": base64.urlsafe_b64encode(nonce).decode("ascii"),
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("ascii"),
    }
    _atomic_write(path, doc)


def get_secret(name: str) -> str:
    key = load_master_key()
    path = _vault_path()
    doc = _load_document(path)
    record = doc["secrets"].get(name)
    if not isinstance(record, dict):
        raise SecretVaultError("secret not found")
    try:
        nonce = base64.urlsafe_b64decode(record["nonce"].encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(record["ciphertext"].encode("ascii"))
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, name.encode("utf-8"))
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise SecretVaultError("secret decryption failed") from exc


def vault_enabled() -> bool:
    value = os.getenv("XBOW_VAULT_ENABLED", "false").strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise SecretVaultError("XBOW_VAULT_ENABLED must be a boolean")
    return value in {"true", "1", "yes", "on"}


def resolve_secret(vault_name: str, env_name: str) -> str | None:
    enabled = vault_enabled()
    inline = os.getenv(env_name)
    if not enabled:
        return inline
    try:
        return get_secret(vault_name)
    except SecretVaultError as exc:
        if inline:
            raise SecretVaultError(
                f"vault enabled but {vault_name} unavailable; refusing environment fallback"
            ) from exc
        raise
