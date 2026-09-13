import base64
import json
import os

import pytest

from app.pentagi_auth import PentagiAuthError, load_pentagi_auth
from app.secret_vault import set_secret


def _vault_key() -> str:
    return base64.urlsafe_b64encode(b"v" * 32).decode("ascii")


def test_pentagi_auth_reads_legacy_env_when_vault_disabled(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_PENTAGI_API_TOKEN", "legacy-token-1234567890")

    auth = load_pentagi_auth()

    assert auth.token == "legacy-token-1234567890"
    assert auth.headers() == {
        "Authorization": "Bearer legacy-token-1234567890",
        "Content-Type": "application/json",
        "User-Agent": "xbow-perso-pentagi/1.0",
    }


def test_pentagi_auth_reads_vault_and_refuses_legacy_fallback(monkeypatch, tmp_path):
    vault_path = tmp_path / "vault.json"
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv("XBOW_VAULT_PATH", str(vault_path))
    monkeypatch.setenv("XBOW_VAULT_MASTER_KEY", _vault_key())
    monkeypatch.delenv("XBOW_PENTAGI_API_TOKEN", raising=False)
    set_secret("pentagi_api_token", "vault-token-123456789012")

    auth = load_pentagi_auth()
    assert auth.token == "vault-token-123456789012"

    monkeypatch.setenv("XBOW_PENTAGI_API_TOKEN", "legacy-token-must-not-win")
    vault_path.write_text(
        json.dumps({"version": 1, "secrets": {}}),
        encoding="utf-8",
    )
    os.chmod(vault_path, 0o600)

    with pytest.raises(PentagiAuthError, match="token is unavailable"):
        load_pentagi_auth()


def test_pentagi_auth_missing_token_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("XBOW_PENTAGI_API_TOKEN", raising=False)

    with pytest.raises(PentagiAuthError, match="not configured"):
        load_pentagi_auth()


@pytest.mark.parametrize(
    "token",
    [
        "short",
        " leading-token-123456",
        "trailing-token-123456 ",
        "token-with-control\n123456",
    ],
)
def test_pentagi_auth_rejects_unsafe_token_values(monkeypatch, token):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_PENTAGI_API_TOKEN", token)

    with pytest.raises(PentagiAuthError):
        load_pentagi_auth()


def test_pentagi_auth_rejects_oversized_token(monkeypatch):
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("XBOW_PENTAGI_API_TOKEN", "x" * 4097)

    with pytest.raises(PentagiAuthError, match="length is invalid"):
        load_pentagi_auth()
