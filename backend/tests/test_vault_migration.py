from __future__ import annotations

import base64
import os

import pytest

from app.secret_vault import get_secret, set_secret
from app.vault_migration import (
    VaultMigrationError,
    apply_vault_migration,
    plan_vault_migration,
    rewrite_env_file,
)


def _master_key() -> str:
    return base64.urlsafe_b64encode(b"k" * 32).decode("ascii")


def _configure(monkeypatch, tmp_path):
    key_file = tmp_path / "master.key"
    key_file.write_text(_master_key(), encoding="utf-8")
    os.chmod(key_file, 0o600)
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY_FILE", str(key_file))
    monkeypatch.delenv("XBOW_VAULT_MASTER_KEY", raising=False)
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "vault.json"))
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    return key_file


def _clear_sources(monkeypatch):
    for name in (
        "XBOW_API_TOKEN",
        "XBOW_API_TOKEN_FILE",
        "XBOW_HACKERONE_API_USERNAME",
        "XBOW_HACKERONE_API_TOKEN",
        "XBOW_PENTAGI_API_TOKEN",
        "LLM_API_KEY",
        "PERPLEXITY_API_KEY",
        "XBOW_AUDIT_HMAC_KEY",
        "XBOW_TOTP_SECRET",
        "XBOW_ALERT_WEBHOOK_HMAC_KEY",
        "XBOW_BROWSER_SECRET_TEST_LOGIN",
        "XBOW_BROWSER_SECRET_TEST_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)


def test_plan_is_redacted(monkeypatch, tmp_path):
    _clear_sources(monkeypatch)
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 40)
    monkeypatch.setenv("XBOW_HACKERONE_API_TOKEN", "super-secret-h1-token")

    result = plan_vault_migration()

    assert result["ok"] is True
    assert result["legacy_sources_found"] == 2
    assert result["contains_secret_values"] is False
    rendered = str(result)
    assert "super-secret-h1-token" not in rendered
    assert "a" * 40 not in rendered


def test_apply_migrates_static_and_browser_secrets(monkeypatch, tmp_path):
    _clear_sources(monkeypatch)
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 40)
    monkeypatch.setenv("XBOW_HACKERONE_API_USERNAME", "researcher")
    monkeypatch.setenv("XBOW_HACKERONE_API_TOKEN", "h1-token-secret")
    monkeypatch.setenv("XBOW_BROWSER_SECRET_TEST_LOGIN", "user@example.test")

    result = apply_vault_migration()

    assert result["ok"] is True
    assert set(result["migrated"]) == {
        "api_token",
        "hackerone_api_username",
        "hackerone_api_token",
        "browser.test_login",
    }
    assert get_secret("api_token") == "a" * 40
    assert get_secret("hackerone_api_username") == "researcher"
    assert get_secret("hackerone_api_token") == "h1-token-secret"
    assert get_secret("browser.test_login") == "user@example.test"
    assert "h1-token-secret" not in str(result)


def test_plan_blocks_conflicting_existing_vault_entry(monkeypatch, tmp_path):
    _clear_sources(monkeypatch)
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_HACKERONE_API_TOKEN", "legacy-value")
    set_secret("hackerone_api_token", "different-value")

    result = plan_vault_migration()

    assert result["ok"] is False
    assert "vault_conflict:hackerone_api_token" in result["blockers"]


def test_api_token_file_is_supported(monkeypatch, tmp_path):
    _clear_sources(monkeypatch)
    _configure(monkeypatch, tmp_path)
    token_file = tmp_path / "api.token"
    token_file.write_text("x" * 40, encoding="utf-8")
    os.chmod(token_file, 0o600)
    monkeypatch.setenv("XBOW_API_TOKEN_FILE", str(token_file))

    result = apply_vault_migration()

    assert result["ok"] is True
    assert get_secret("api_token") == "x" * 40
    assert "XBOW_API_TOKEN_FILE" in result["legacy_sources_to_clear"]


def test_conflicting_api_token_sources_fail_closed(monkeypatch, tmp_path):
    _clear_sources(monkeypatch)
    _configure(monkeypatch, tmp_path)
    token_file = tmp_path / "api.token"
    token_file.write_text("x" * 40, encoding="utf-8")
    os.chmod(token_file, 0o600)
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 40)
    monkeypatch.setenv("XBOW_API_TOKEN_FILE", str(token_file))

    with pytest.raises(VaultMigrationError, match="conflicting legacy sources"):
        plan_vault_migration()


def test_inline_master_key_is_rejected(monkeypatch, tmp_path):
    _clear_sources(monkeypatch)
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY", _master_key())

    with pytest.raises(VaultMigrationError, match="inline vault master key"):
        plan_vault_migration()


def test_rewrite_env_requires_verified_vault_values(monkeypatch, tmp_path):
    _clear_sources(monkeypatch)
    key_file = _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 40)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DRY_RUN=true\nXBOW_API_TOKEN=" + "a" * 40 + "\nXBOW_VAULT_ENABLED=false\n",
        encoding="utf-8",
    )
    os.chmod(env_file, 0o600)

    with pytest.raises(VaultMigrationError, match="before vault verification"):
        rewrite_env_file(str(env_file))

    apply_vault_migration()
    result = rewrite_env_file(str(env_file))

    rendered = env_file.read_text(encoding="utf-8")
    assert result["ok"] is True
    assert "XBOW_API_TOKEN=" not in rendered
    assert "XBOW_VAULT_ENABLED=true" in rendered
    assert f"XBOW_VAULT_MASTER_KEY_FILE={key_file}" in rendered
    assert (tmp_path / ".env.pre-vault.bak").exists()


def test_rewrite_env_removes_browser_secret_assignments(monkeypatch, tmp_path):
    _clear_sources(monkeypatch)
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv("XBOW_BROWSER_SECRET_TEST_PASSWORD", "password-secret")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DRY_RUN=true\nXBOW_BROWSER_SECRET_TEST_PASSWORD=password-secret\n",
        encoding="utf-8",
    )
    os.chmod(env_file, 0o600)

    apply_vault_migration()
    rewrite_env_file(str(env_file))

    rendered = env_file.read_text(encoding="utf-8")
    assert "XBOW_BROWSER_SECRET_TEST_PASSWORD=" not in rendered
    assert "DRY_RUN=true" in rendered
