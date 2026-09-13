import pytest

from app.pentagi_broker_auth import (
    PentagiBrokerAuthError,
    load_pentagi_broker_auth,
)


def test_broker_auth_reads_explicit_fallback(monkeypatch):
    monkeypatch.setenv(
        "XBOW_PENTAGI_BROKER_TOKEN",
        "broker-token-with-at-least-sixteen-chars",
    )
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")

    auth = load_pentagi_broker_auth()

    assert auth.token == "broker-token-with-at-least-sixteen-chars"
    assert "broker-token" not in repr(auth)


def test_broker_auth_rejects_short_token(monkeypatch):
    monkeypatch.setenv("XBOW_PENTAGI_BROKER_TOKEN", "short")
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "false")

    with pytest.raises(PentagiBrokerAuthError, match="length is invalid"):
        load_pentagi_broker_auth()
