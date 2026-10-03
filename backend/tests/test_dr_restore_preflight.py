import base64
import json

from app.dr_manifest import build_backup_manifest, write_backup_manifest
from app.dr_restore_preflight import assess_restore_preflight


def _write_valid_backup_set(tmp_path):
    postgres = tmp_path / "postgres.dump"
    redis = tmp_path / "dump.rdb"
    vault = tmp_path / "secrets.vault.json"
    manifest = tmp_path / "manifest.json"

    postgres.write_bytes(b"PGDMP" + b"\x00" * 64)
    redis.write_bytes(b"REDIS0011" + b"\x00" * 64)
    vault.write_text(
        json.dumps(
            {
                "version": 1,
                "secrets": {
                    "api_token": {
                        "nonce": base64.urlsafe_b64encode(b"n" * 12).decode("ascii"),
                        "ciphertext": base64.urlsafe_b64encode(b"c" * 32).decode("ascii"),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest),
    )
    return manifest, postgres, redis, vault


def test_restore_preflight_accepts_recognized_integrity_valid_backup_set(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    manifest, postgres, redis, vault = _write_valid_backup_set(tmp_path)

    result = assess_restore_preflight(
        str(manifest),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["restore_preflight_ready"] is True
    assert result["integrity_valid"] is True
    assert result["artifacts"]["postgres"]["format"] == "custom"
    assert result["artifacts"]["redis"]["format"] == "rdb"
    assert result["artifacts"]["redis"]["rdb_version"] == 11
    assert result["artifacts"]["vault"]["format"] == "xbow_vault_v1"
    assert result["artifacts"]["vault"]["secret_count"] == 1
    assert result["actual_restore_tested"] is False
    assert result["automatic_restore"] is False
    assert result["non_destructive"] is True


def test_restore_preflight_rejects_checksum_valid_but_unrecognized_redis_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    manifest, postgres, redis, vault = _write_valid_backup_set(tmp_path)

    redis.write_bytes(b"not-an-rdb")
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest),
    )

    result = assess_restore_preflight(
        str(manifest),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["integrity_valid"] is True
    assert result["restore_preflight_ready"] is False
    assert "redis_snapshot_format_unrecognized" in result["blockers"]


def test_restore_preflight_rejects_unrecognized_postgres_dump(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    manifest, postgres, redis, vault = _write_valid_backup_set(tmp_path)

    postgres.write_bytes(b"not-a-postgres-dump")
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest),
    )

    result = assess_restore_preflight(
        str(manifest),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["restore_preflight_ready"] is False
    assert "postgres_dump_format_unrecognized" in result["blockers"]


def test_restore_preflight_rejects_invalid_vault_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    manifest, postgres, redis, vault = _write_valid_backup_set(tmp_path)

    vault.write_text(
        json.dumps(
            {
                "version": 1,
                "secrets": {
                    "api_token": {
                        "nonce": "not-base64!",
                        "ciphertext": "not-base64!",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest),
    )

    result = assess_restore_preflight(
        str(manifest),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["restore_preflight_ready"] is False
    assert "vault_backup_format_unrecognized" in result["blockers"]


def test_restore_preflight_does_not_expose_secret_names_or_backup_contents(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    manifest, postgres, redis, vault = _write_valid_backup_set(tmp_path)

    result = assess_restore_preflight(
        str(manifest),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )
    rendered = json.dumps(result, sort_keys=True)

    assert "api_token" not in rendered
    assert "PGDMP" not in rendered
    assert "REDIS0011" not in rendered
    assert result["contains_backup_contents"] is False
    assert result["contains_secrets"] is False
    assert result["contains_secret_names"] is False
