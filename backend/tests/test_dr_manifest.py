from pathlib import Path

import pytest

from app.dr_manifest import (
    DisasterRecoveryError,
    build_backup_manifest,
    verify_backup_manifest,
    write_backup_manifest,
)


def _files(tmp_path):
    postgres = tmp_path / "postgres.dump"
    redis = tmp_path / "dump.rdb"
    vault = tmp_path / "secrets.vault.json"
    postgres.write_bytes(b"postgres-backup")
    redis.write_bytes(b"redis-backup")
    vault.write_bytes(b"vault-backup")
    return postgres, redis, vault


def test_backup_manifest_contains_only_integrity_metadata(tmp_path):
    postgres, redis, vault = _files(tmp_path)

    manifest = build_backup_manifest(
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert manifest["version"] == 1
    assert manifest["contains_secrets"] is False
    assert manifest["contains_backup_contents"] is False
    assert {item["kind"] for item in manifest["artifacts"]} == {
        "postgres",
        "redis",
        "vault",
    }
    rendered = str(manifest)
    assert "postgres-backup" not in rendered
    assert "redis-backup" not in rendered
    assert "vault-backup" not in rendered


def test_manifest_roundtrip_verifies(tmp_path):
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = build_backup_manifest(
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )
    write_backup_manifest(manifest, str(manifest_path))

    result = verify_backup_manifest(
        str(manifest_path),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["valid"] is True
    assert all(item["valid"] for item in result["artifacts"].values())
    assert oct(manifest_path.stat().st_mode & 0o777) == "0o600"


def test_manifest_detects_modified_backup(tmp_path):
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = build_backup_manifest(
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )
    write_backup_manifest(manifest, str(manifest_path))
    redis.write_bytes(b"modified-redis-backup")

    result = verify_backup_manifest(
        str(manifest_path),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["valid"] is False
    assert result["artifacts"]["redis"]["valid"] is False


def test_manifest_rejects_symlink_backup(tmp_path):
    postgres, redis, vault = _files(tmp_path)
    symlink = tmp_path / "postgres-link.dump"
    symlink.symlink_to(postgres)

    with pytest.raises(DisasterRecoveryError, match="postgres backup file is unavailable"):
        build_backup_manifest(
            postgres_dump=str(symlink),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        )


def test_manifest_rejects_empty_backup(tmp_path):
    postgres, redis, vault = _files(tmp_path)
    postgres.write_bytes(b"")

    with pytest.raises(DisasterRecoveryError, match="postgres backup file is empty"):
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        )


def test_manifest_rejects_symlink_destination(tmp_path):
    postgres, redis, vault = _files(tmp_path)
    manifest = build_backup_manifest(
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "manifest.json"
    link.symlink_to(real)

    with pytest.raises(DisasterRecoveryError, match="must not be a symlink"):
        write_backup_manifest(manifest, str(link))
