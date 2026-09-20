from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from pathlib import Path
from typing import Any

from .secret_vault import SecretVaultError, get_secret, set_secret


_STATIC_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("hackerone_api_username", "XBOW_HACKERONE_API_USERNAME"),
    ("hackerone_api_token", "XBOW_HACKERONE_API_TOKEN"),
    ("pentagi_api_token", "XBOW_PENTAGI_API_TOKEN"),
    ("llm_api_key", "LLM_API_KEY"),
    ("perplexity_api_key", "PERPLEXITY_API_KEY"),
    ("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY"),
    ("totp_secret", "XBOW_TOTP_SECRET"),
    ("alert_webhook_hmac_key", "XBOW_ALERT_WEBHOOK_HMAC_KEY"),
)
_BROWSER_PREFIX = "XBOW_BROWSER_SECRET_"
_RELEVANT_STATIC_ENV = {
    "XBOW_API_TOKEN",
    "XBOW_API_TOKEN_FILE",
    *(env_name for _vault_name, env_name in _STATIC_MAPPINGS),
}


class VaultMigrationError(RuntimeError):
    pass


def _safe_secret_file(path_value: str) -> str:
    path = Path(path_value)
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("not a regular file")
        stat = path.stat()
        if stat.st_mode & 0o077:
            raise OSError("permissions too broad")
        if not 1 <= stat.st_size <= 16384:
            raise OSError("unsafe secret file size")
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise VaultMigrationError("legacy API token file is unavailable") from exc
    if not value:
        raise VaultMigrationError("legacy API token file is empty")
    return value


def _decode_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def _source_env_file(path_value: str) -> dict[str, str]:
    path = Path(path_value)
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("not a regular file")
        stat = path.stat()
        if stat.st_mode & 0o077:
            raise OSError("permissions too broad")
        if stat.st_size > 1024 * 1024:
            raise OSError("environment file too large")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise VaultMigrationError("source environment file is unavailable") from exc

    values: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").lstrip()
        if "=" not in stripped:
            continue
        name, raw_value = stripped.split("=", 1)
        name = name.strip()
        relevant = name in _RELEVANT_STATIC_ENV or name.startswith(_BROWSER_PREFIX)
        if not relevant:
            continue
        if not name or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in name):
            raise VaultMigrationError(
                f"invalid relevant environment name at line {line_number}"
            )
        value = _decode_env_value(raw_value)
        existing = values.get(name)
        if existing is not None and existing != value:
            raise VaultMigrationError(f"conflicting duplicate source for {name}")
        values[name] = value
    return values


def _merged_source_environment(source_env_file: str | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    if source_env_file:
        values.update(_source_env_file(source_env_file))

    for name, value in os.environ.items():
        relevant = name in _RELEVANT_STATIC_ENV or name.startswith(_BROWSER_PREFIX)
        if not relevant or not value:
            continue
        existing = values.get(name)
        if existing is not None and existing != value:
            raise VaultMigrationError(f"conflicting process/file source for {name}")
        values[name] = value
    return values


def _legacy_sources(source_env_file: str | None = None) -> dict[str, tuple[str, str]]:
    """Return vault_name -> (source_name, value) without exposing values externally."""
    env = _merged_source_environment(source_env_file)
    result: dict[str, tuple[str, str]] = {}

    inline_api = (env.get("XBOW_API_TOKEN") or "").strip()
    api_file = (env.get("XBOW_API_TOKEN_FILE") or "").strip()
    if inline_api and api_file:
        raise VaultMigrationError("API token has conflicting legacy sources")
    if inline_api:
        result["api_token"] = ("XBOW_API_TOKEN", inline_api)
    elif api_file:
        result["api_token"] = ("XBOW_API_TOKEN_FILE", _safe_secret_file(api_file))

    for vault_name, env_name in _STATIC_MAPPINGS:
        value = env.get(env_name)
        if value:
            result[vault_name] = (env_name, value)

    for env_name, value in env.items():
        if not env_name.startswith(_BROWSER_PREFIX) or not value:
            continue
        suffix = env_name.removeprefix(_BROWSER_PREFIX).strip().lower()
        if not suffix or any(
            ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in suffix
        ):
            raise VaultMigrationError("browser secret environment name is invalid")
        result[f"browser.{suffix}"] = (env_name, value)

    return result


def _vault_key_file() -> Path:
    inline = (os.getenv("XBOW_VAULT_MASTER_KEY") or "").strip()
    raw = (os.getenv("XBOW_VAULT_MASTER_KEY_FILE") or "").strip()
    if inline:
        raise VaultMigrationError("inline vault master key is forbidden for migration")
    if not raw:
        raise VaultMigrationError("XBOW_VAULT_MASTER_KEY_FILE is required")
    path = Path(raw)
    if path.is_symlink():
        raise VaultMigrationError("vault master key file must not be a symlink")
    return path


def _vault_path() -> Path:
    raw = (os.getenv("XBOW_VAULT_PATH") or "/data/secrets.vault.json").strip()
    path = Path(raw)
    if path.is_symlink():
        raise VaultMigrationError("vault path must not be a symlink")
    return path


def _validate_master_key_file(path: Path) -> None:
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_mode & 0o077 or stat.st_size > 256:
            raise OSError("unsafe master key file")
        existing = path.read_text(encoding="utf-8").strip()
        decoded = base64.urlsafe_b64decode(existing.encode("ascii"))
        if len(decoded) != 32:
            raise ValueError("invalid key length")
    except (OSError, UnicodeError, ValueError) as exc:
        raise VaultMigrationError("existing vault master key file is invalid") from exc


def ensure_master_key_file() -> dict[str, Any]:
    path = _vault_key_file()
    if path.exists():
        _validate_master_key_file(path)
        return {"created": False, "master_key_file_ready": True}

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    try:
        with path.open("x", encoding="utf-8") as handle:
            os.chmod(path, 0o600)
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise VaultMigrationError("unable to create vault master key file") from exc
    return {"created": True, "master_key_file_ready": True}


def _existing_matches(name: str, value: str) -> bool | None:
    try:
        current = get_secret(name)
    except SecretVaultError as exc:
        if str(exc) == "secret not found":
            return None
        raise VaultMigrationError("existing vault could not be verified") from exc
    return current == value


def plan_vault_migration(source_env_file: str | None = None) -> dict[str, Any]:
    key_path = _vault_key_file()
    vault_path = _vault_path()
    sources = _legacy_sources(source_env_file)
    entries: list[dict[str, Any]] = []
    blockers: list[str] = []

    key_ready = key_path.exists()
    if key_ready:
        _validate_master_key_file(key_path)
    elif vault_path.exists():
        blockers.append("vault_master_key_missing_for_existing_vault")

    for vault_name, (source_name, value) in sorted(sources.items()):
        if vault_path.exists() and key_ready:
            match = _existing_matches(vault_name, value)
        else:
            match = None

        if "vault_master_key_missing_for_existing_vault" in blockers:
            status = "unverified"
        elif match is False:
            blockers.append(f"vault_conflict:{vault_name}")
            status = "conflict"
        elif match is True:
            status = "already_migrated"
        else:
            status = "ready"

        entries.append(
            {
                "vault_name": vault_name,
                "source_name": source_name,
                "status": status,
            }
        )

    return {
        "ok": not blockers,
        "legacy_sources_found": len(sources),
        "entries": entries,
        "blockers": blockers,
        "contains_secret_values": False,
        "master_key_file_ready": key_ready,
        "master_key_will_be_created_on_apply": not key_ready and not vault_path.exists(),
        "vault_enabled_after_apply": False,
        "requires_legacy_source_cleanup": bool(sources),
    }


def apply_vault_migration(source_env_file: str | None = None) -> dict[str, Any]:
    key_state = ensure_master_key_file()
    plan = plan_vault_migration(source_env_file)
    if not plan["ok"]:
        raise VaultMigrationError(
            "vault migration blocked by existing conflicting entries"
        )

    sources = _legacy_sources(source_env_file)
    migrated: list[str] = []
    already: list[str] = []
    source_names: list[str] = []

    for vault_name, (source_name, value) in sorted(sources.items()):
        match = _existing_matches(vault_name, value)
        if match is True:
            already.append(vault_name)
        else:
            set_secret(vault_name, value)
            if _existing_matches(vault_name, value) is not True:
                raise VaultMigrationError("vault write verification failed")
            migrated.append(vault_name)
        source_names.append(source_name)

    return {
        "ok": True,
        "master_key_file_created": bool(key_state["created"]),
        "migrated": migrated,
        "already_migrated": already,
        "legacy_sources_to_clear": sorted(set(source_names)),
        "next_step": "clear legacy secret sources, then set XBOW_VAULT_ENABLED=true",
        "contains_secret_values": False,
    }


def rewrite_env_file(
    path_value: str,
    *,
    source_env_file: str | None = None,
) -> dict[str, Any]:
    """Remove migrated legacy secret assignments and enable vault atomically."""
    path = Path(path_value)
    if path.is_symlink() or not path.is_file():
        raise VaultMigrationError("environment file is unavailable")
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise VaultMigrationError("environment file is unavailable") from exc

    sources = _legacy_sources(source_env_file or path_value)
    if not sources:
        raise VaultMigrationError("no legacy secret sources are present to rewrite")

    for vault_name, (_source_name, value) in sources.items():
        if _existing_matches(vault_name, value) is not True:
            raise VaultMigrationError("refusing env rewrite before vault verification")

    names = {source for source, _value in sources.values()}
    names.add("XBOW_VAULT_ENABLED")
    names.add("XBOW_VAULT_MASTER_KEY")
    names.add("XBOW_VAULT_MASTER_KEY_FILE")
    key_file = str(_vault_key_file())

    kept: list[str] = []
    for line in original.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            kept.append(line)
            continue
        candidate = stripped.removeprefix("export ").lstrip()
        name = candidate.split("=", 1)[0].strip()
        if name in names or name.startswith(_BROWSER_PREFIX):
            continue
        kept.append(line)

    kept.extend(
        [
            "XBOW_VAULT_ENABLED=true",
            f"XBOW_VAULT_MASTER_KEY_FILE={key_file}",
        ]
    )
    rendered = "\n".join(kept).rstrip() + "\n"
    tmp = path.with_name(path.name + ".vault-migrate.tmp")
    backup = path.with_name(path.name + ".pre-vault.bak")
    if backup.exists():
        raise VaultMigrationError("environment backup already exists")
    try:
        backup.write_text(original, encoding="utf-8")
        os.chmod(backup, 0o600)
        with tmp.open("x", encoding="utf-8") as handle:
            os.chmod(tmp, 0o600)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise VaultMigrationError("environment rewrite failed") from exc

    return {
        "ok": True,
        "backup_created": True,
        "backup_filename": backup.name,
        "vault_enabled": True,
        "legacy_assignments_removed": len(
            names
            - {
                "XBOW_VAULT_ENABLED",
                "XBOW_VAULT_MASTER_KEY",
                "XBOW_VAULT_MASTER_KEY_FILE",
            }
        ),
        "contains_secret_values": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.vault_migration",
        description="Migrate legacy xbow secret sources into the encrypted vault.",
    )
    parser.add_argument("command", choices=("plan", "apply", "rewrite-env"))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--source-env-file",
        default=None,
        help="Optional private env file used as a legacy secret source.",
    )
    args = parser.parse_args()

    try:
        if args.command == "plan":
            result = plan_vault_migration(args.source_env_file)
        elif args.command == "apply":
            result = apply_vault_migration(args.source_env_file)
        else:
            result = rewrite_env_file(
                args.env_file,
                source_env_file=args.source_env_file or args.env_file,
            )
    except (VaultMigrationError, SecretVaultError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "contains_secret_values": False,
                },
                sort_keys=True,
            )
        )
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
