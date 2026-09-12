import asyncio
import base64

import pytest
from starlette.requests import Request

from app.auth import AuthError
from app.main import authenticate_control_api
from app.secret_vault import set_secret
from app.totp_auth import _totp, configured_totp_secret, require_totp_for_mutation, verify_totp_code


RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def _request(method="POST", headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/campaigns",
            "headers": raw,
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1234),
            "scheme": "https",
        }
    )


def _clear(monkeypatch):
    for name in (
        "XBOW_TOTP_ENABLED",
        "XBOW_TOTP_SECRET",
        "XBOW_API_TOKEN",
        "XBOW_API_TOKEN_FILE",
        "XBOW_VAULT_ENABLED",
        "XBOW_VAULT_MASTER_KEY",
        "XBOW_VAULT_MASTER_KEY_FILE",
        "XBOW_VAULT_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_totp_matches_rfc6238_sha1_vector(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_TOTP_SECRET", RFC_SECRET)

    secret = configured_totp_secret()

    assert _totp(secret, 1) == "287082"
    assert verify_totp_code("287082", now=59) is True


def test_totp_disabled_preserves_mutating_api_compatibility(monkeypatch):
    _clear(monkeypatch)

    require_totp_for_mutation(_request("POST"))


def test_totp_enabled_requires_code_for_mutation(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_TOTP_ENABLED", "true")
    monkeypatch.setenv("XBOW_TOTP_SECRET", RFC_SECRET)

    with pytest.raises(AuthError) as exc:
        require_totp_for_mutation(_request("POST"))

    assert exc.value.status_code == 401
    assert exc.value.detail == "TOTP code required"


def test_totp_enabled_does_not_require_code_for_get(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_TOTP_ENABLED", "true")
    monkeypatch.setenv("XBOW_TOTP_SECRET", RFC_SECRET)

    require_totp_for_mutation(_request("GET"))


def test_totp_rejects_invalid_code(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_TOTP_ENABLED", "true")
    monkeypatch.setenv("XBOW_TOTP_SECRET", RFC_SECRET)

    with pytest.raises(AuthError) as exc:
        require_totp_for_mutation(_request("DELETE", {"X-TOTP-Code": "000000"}))

    assert exc.value.status_code == 403


def test_totp_accepts_adjacent_time_step(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_TOTP_SECRET", RFC_SECRET)
    secret = configured_totp_secret()
    code = _totp(secret, 2)

    assert verify_totp_code(code, now=30) is True


def test_totp_vault_secret_is_supported(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv(
        "XBOW_VAULT_MASTER_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "vault.json"))
    set_secret("totp_secret", RFC_SECRET)

    assert configured_totp_secret()


def test_totp_vault_mode_refuses_env_fallback(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_VAULT_ENABLED", "true")
    monkeypatch.setenv(
        "XBOW_VAULT_MASTER_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )
    monkeypatch.setenv("XBOW_VAULT_PATH", str(tmp_path / "vault.json"))
    monkeypatch.setenv("XBOW_TOTP_SECRET", RFC_SECRET)

    with pytest.raises(AuthError) as exc:
        configured_totp_secret()

    assert exc.value.status_code == 503
    assert "conflicting legacy secret sources" in exc.value.detail


def test_control_middleware_requires_token_and_totp_for_mutation(monkeypatch):
    _clear(monkeypatch)
    token = "control-token-" + "x" * 32
    monkeypatch.setenv("XBOW_API_TOKEN", token)
    monkeypatch.setenv("XBOW_TOTP_ENABLED", "true")
    monkeypatch.setenv("XBOW_TOTP_SECRET", RFC_SECRET)
    secret = configured_totp_secret()
    code = _totp(secret, 1)

    async def call_next(_request):
        return object()

    import app.totp_auth as totp_auth

    monkeypatch.setattr(totp_auth.time, "time", lambda: 30.0)
    result = asyncio.run(
        authenticate_control_api(
            _request(
                "POST",
                {
                    "Authorization": f"Bearer {token}",
                    "X-TOTP-Code": code,
                },
            ),
            call_next,
        )
    )

    assert result is not None


def test_invalid_totp_configuration_fails_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("XBOW_TOTP_ENABLED", "true")
    monkeypatch.setenv("XBOW_TOTP_SECRET", "not-base32!")

    with pytest.raises(AuthError) as exc:
        require_totp_for_mutation(_request("POST", {"X-TOTP-Code": "123456"}))

    assert exc.value.status_code == 503
