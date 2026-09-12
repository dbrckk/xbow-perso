import base64
import json
import os

import pytest

from app.secret_vault import (
    SecretVaultError,
    get_secret,
    resolve_secret,
    set_secret,
)


def _master_key():
    return base64.urlsafe_b64encode(b"k" * 32).decode("ascii")


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY", _master_key())
    monkeypatch.delenv("XBOW_VAULT_MASTER_KEY_FILE", raising=False)
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "secrets.vault.json"))


def test_vault_encrypts_secret_at_rest(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)

    set_secret("audit_hmac_key", "super-secret-value")

    path = tmp_path / "secrets.vault.json"
    raw = path.read_text(encoding="utf-8")
    assert "super-secret-value" not in raw
    document = json.loads(raw)
    assert document["version"] == 1
    assert document["secrets"]["audit_hmac_key"]["ciphertext"]
    assert get_secret("audit_hmac_key") == "super-secret-value"
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_vault_detects_ciphertext_tampering(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    set_secret("audit_hmac_key", "super-secret-value")
    path = tmp_path / "secrets.vault.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    ciphertext = document["secrets"]["audit_hmac_key"]["ciphertext"]
    document["secrets"]["audit_hmac_key"]["ciphertext"] = ciphertext[:-2] + "AA"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SecretVaultError, match="decryption failed"):
        get_secret("audit_hmac_key")


def test_vault_rejects_wrong_master_key(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    set_secret("audit_hmac_key", "super-secret-value")
    monkeypatch.setenv(
        "XBOW_VAULT_MASTER_KEY",
        base64.urlsafe_b64encode(b"x" * 32).decode("ascii"),
    )

    with pytest.raises(SecretVaultError, match="decryption failed"):
        get_secret("audit_hmac_key")


def test_vault_master_key_file_is_supported(monkeypatch, tmp_path):
    key_file = tmp_path / "master.key"
    key_file.write_text(_master_key(), encoding="utf-8")
    os.chmod(key_file, 0o600)
    monkeypatch.delenv("XBOW_VAULT_MASTER_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY_FILE", str(key_file))
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "vault.json"))

    set_secret("audit_hmac_key", "from-file")

    assert get_secret("audit_hmac_key") == "from-file"


def test_vault_rejects_conflicting_master_key_sources(monkeypatch, tmp_path):
    key_file = tmp_path / "master.key"
    key_file.write_text(_master_key(), encoding="utf-8")
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY", _master_key())
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY_FILE", str(key_file))

    with pytest.raises(SecretVaultError, match="conflicting sources"):
        set_secret("audit_hmac_key", "secret")


def test_resolve_secret_preserves_env_compatibility_when_vault_disabled(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "legacy-env-secret")

    assert resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY") == "legacy-env-secret"


def test_resolve_secret_uses_vault_and_refuses_env_fallback(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv("XBOW_AUDIT_HMAC_KEY", "must-not-fallback")
    set_secret("audit_hmac_key", "vault-secret")

    assert resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY") == "vault-secret"

    document = json.loads((tmp_path / "secrets.vault.json").read_text(encoding="utf-8"))
    document["secrets"].pop("audit_hmac_key")
    (tmp_path / "secrets.vault.json").write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SecretVaultError, match="refusing environment fallback"):
        resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")


def test_vault_rejects_broad_master_key_permissions(monkeypatch, tmp_path):
    key_file = tmp_path / "master.key"
    key_file.write_text(_master_key(), encoding="utf-8")
    os.chmod(key_file, 0o644)
    monkeypatch.delenv("XBOW_VAULT_MASTER_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY_FILE", str(key_file))
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "vault.json"))

    with pytest.raises(SecretVaultError, match="master key file is unavailable"):
        set_secret("audit_hmac_key", "secret")


def test_vault_rejects_broad_existing_vault_permissions(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    set_secret("audit_hmac_key", "secret")
    path = tmp_path / "secrets.vault.json"
    os.chmod(path, 0o644)

    with pytest.raises(SecretVaultError, match="vault file is invalid"):
        get_secret("audit_hmac_key")
