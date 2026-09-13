import hashlib
import hmac
import json

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


def _canonical_legacy_v1(manifest):
    payload = {
        key: value
        for key, value in manifest.items()
        if key
        not in {
            "manifest_signature",
            "manifest_signature_alg",
            "integrity_mode",
        }
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


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


def test_manifest_rejects_invalid_artifact_size_schema(tmp_path):
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = build_backup_manifest(
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )
    manifest["artifacts"][0]["size_bytes"] = "not-an-int"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DisasterRecoveryError, match="artifact size is invalid"):
        verify_backup_manifest(
            str(manifest_path),
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        )


def test_signed_manifest_detects_manifest_rewrite(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "dr-signing-key")
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = build_backup_manifest(
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )
    write_backup_manifest(manifest, str(manifest_path))

    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["version"] == 2
    assert saved["manifest_signature_alg"] == "hmac-sha256"
    assert saved["integrity_mode"] == "sha256-artifacts+hmac-sha256-manifest"
    assert len(saved["manifest_signature"]) == 64

    saved["artifacts"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(saved), encoding="utf-8")

    result = verify_backup_manifest(
        str(manifest_path),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["valid"] is False
    assert result["manifest_signature_valid"] is False


def test_signed_manifest_rejects_signature_field_stripping(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "dr-signing-key")
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest_path),
    )

    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["version"] == 2
    for field in (
        "manifest_signature",
        "manifest_signature_alg",
        "integrity_mode",
    ):
        saved.pop(field, None)
    manifest_path.write_text(json.dumps(saved), encoding="utf-8")

    with pytest.raises(
        DisasterRecoveryError,
        match="authentication metadata is missing or invalid",
    ):
        verify_backup_manifest(
            str(manifest_path),
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        )


def test_signed_manifest_authenticates_integrity_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "dr-signing-key")
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest_path),
    )

    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    saved["integrity_mode"] = "sha256-artifacts"
    manifest_path.write_text(json.dumps(saved), encoding="utf-8")

    with pytest.raises(
        DisasterRecoveryError,
        match="authentication metadata is missing or invalid",
    ):
        verify_backup_manifest(
            str(manifest_path),
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        )


def test_signed_manifest_requires_matching_verification_key(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "correct-key")
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest_path),
    )
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "wrong-key")

    result = verify_backup_manifest(
        str(manifest_path),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["valid"] is False
    assert result["manifest_signature_valid"] is False


def test_unsigned_manifest_remains_backward_compatible(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest_path),
    )

    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["version"] == 1
    assert saved["manifest_signature"] is None

    result = verify_backup_manifest(
        str(manifest_path),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["valid"] is True
    assert result["manifest_signature_valid"] is None


def test_legacy_signed_v1_manifest_remains_backward_compatible(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "legacy-key")
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = build_backup_manifest(
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )
    manifest["manifest_signature_alg"] = "hmac-sha256"
    manifest["integrity_mode"] = "sha256-artifacts+hmac-sha256-manifest"
    manifest["manifest_signature"] = hmac.new(
        b"legacy-key",
        _canonical_legacy_v1(manifest),
        hashlib.sha256,
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verify_backup_manifest(
        str(manifest_path),
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )

    assert result["valid"] is True
    assert result["manifest_signature_valid"] is True


def test_legacy_v1_rejects_partial_signature_stripping(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = build_backup_manifest(
        postgres_dump=str(postgres),
        redis_snapshot=str(redis),
        vault_copy=str(vault),
    )
    manifest["manifest_signature_alg"] = "hmac-sha256"
    manifest["integrity_mode"] = "sha256-artifacts+hmac-sha256-manifest"
    manifest["manifest_signature"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        DisasterRecoveryError,
        match="signature metadata is inconsistent",
    ):
        verify_backup_manifest(
            str(manifest_path),
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        )


def test_signed_manifest_fails_closed_when_key_becomes_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "correct-key")
    postgres, redis, vault = _files(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_backup_manifest(
        build_backup_manifest(
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        ),
        str(manifest_path),
    )
    monkeypatch.delenv("XBOW_AUDIT_HMAC_KEY", raising=False)

    with pytest.raises(DisasterRecoveryError, match="verification key is unavailable"):
        verify_backup_manifest(
            str(manifest_path),
            postgres_dump=str(postgres),
            redis_snapshot=str(redis),
            vault_copy=str(vault),
        )
