import pytest
from starlette.requests import Request

from app.auth import AuthError, configured_api_token, require_api_token


def request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/api/campaigns", "headers": raw, "query_string": b"", "server": ("test", 80), "client": ("test", 1234), "scheme": "http"})


def test_missing_server_token_fails_closed(monkeypatch):
    monkeypatch.delenv("XBOW_API_TOKEN", raising=False)
    with pytest.raises(AuthError) as exc:
        configured_api_token()
    assert exc.value.status_code == 503


def test_short_server_token_fails_closed(monkeypatch):
    monkeypatch.setenv("XBOW_API_TOKEN", "too-short")
    with pytest.raises(AuthError) as exc:
        configured_api_token()
    assert exc.value.status_code == 503


def test_missing_client_token_is_unauthorized(monkeypatch):
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 32)
    with pytest.raises(AuthError) as exc:
        require_api_token(request())
    assert exc.value.status_code == 401


def test_wrong_client_token_is_forbidden(monkeypatch):
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 32)
    with pytest.raises(AuthError) as exc:
        require_api_token(request({"Authorization": "Bearer " + "b" * 32}))
    assert exc.value.status_code == 403


def test_bearer_token_is_accepted(monkeypatch):
    token = "correct-token-" + "x" * 32
    monkeypatch.setenv("XBOW_API_TOKEN", token)
    require_api_token(request({"Authorization": f"Bearer {token}"}))


def test_x_api_key_fallback_is_accepted(monkeypatch):
    token = "mobile-token-" + "y" * 32
    monkeypatch.setenv("XBOW_API_TOKEN", token)
    require_api_token(request({"X-API-Key": token}))
