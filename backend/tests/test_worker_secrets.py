import base64

import pytest

from app.secret_vault import set_secret
from app.worker import WorkerPolicyError, _worker_env


def _clear(monkeypatch):
    for name in (
        "XBOW_VAULT_ENABLED",
        "XBOW_VAULT_MASTER_KEY",
        "XBOW_VAULT_MASTER_KEY_FILE",
        "XBOW_VAULT_PATH",
        "LLM_API_KEY",
        "PERPLEXITY_API_KEY",
        "LLM_API_BASE",
        "STRIX_LLM",
        "STRIX_REASONING_EFFORT",
    ):
        monkeypatch.delenv(name, raising=False)


def _configure_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv(
        "XBOW_VAULT_MASTER_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "vault.json"))


def test_worker_env_preserves_legacy_provider_secrets_when_vault_disabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "legacy-llm")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "legacy-perplexity")

    env = _worker_env()

    assert env["LLM_API_KEY"] == "legacy-llm"
    assert env["PERPLEXITY_API_KEY"] == "legacy-perplexity"


def test_worker_env_loads_scanner_secrets_from_vault(monkeypatch, tmp_path):
    _clear(monkeypatch)
    _configure_vault(monkeypatch, tmp_path)
    set_secret("llm_api_key", "vault-llm")
    set_secret("perplexity_api_key", "vault-perplexity")

    env = _worker_env()

    assert env["LLM_API_KEY"] == "vault-llm"
    assert env["PERPLEXITY_API_KEY"] == "vault-perplexity"


def test_worker_env_keeps_unused_vault_secrets_optional(monkeypatch, tmp_path):
    _clear(monkeypatch)
    _configure_vault(monkeypatch, tmp_path)
    set_secret("llm_api_key", "vault-llm")

    env = _worker_env()

    assert env["LLM_API_KEY"] == "vault-llm"
    assert "PERPLEXITY_API_KEY" not in env


def test_worker_env_refuses_legacy_secret_fallback_when_vault_enabled(monkeypatch, tmp_path):
    _clear(monkeypatch)
    _configure_vault(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "must-not-fallback")

    with pytest.raises(WorkerPolicyError, match="legacy LLM_API_KEY fallback is forbidden"):
        _worker_env()


def test_worker_env_does_not_inherit_unrelated_secrets(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABASE_PASSWORD", "must-not-leak")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = _worker_env()

    assert env["PATH"] == "/usr/bin"
    assert "DATABASE_PASSWORD" not in env
