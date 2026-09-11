import asyncio

import pytest
from starlette.requests import Request

from app.auth import AuthError, configured_api_token, require_api_token
from app.main import authenticate_control_api


def request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/api/campaigns", "headers": raw, "query_string": b"", "server": ("test", 80), "client": ("test", 1234), "scheme": "http"})


def clear_secret_env(monkeypatch):
    monkeypatch.delenv("XBOW_API_TOKEN", raising=False)
    monkeypatch.delenv("XBOW_API_TOKEN_FILE", raising=False)


def test_missing_server_token_fails_closed(monkeypatch):
    clear_secret_env(monkeypatch)
    with pytest.raises(AuthError) as exc:
        configured_api_token()
    assert exc.value.status_code == 503


def test_short_server_token_fails_closed(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN", "too-short")
    with pytest.raises(AuthError) as exc:
        configured_api_token()
    assert exc.value.status_code == 503


def test_file_backed_secret_is_supported(monkeypatch, tmp_path):
    clear_secret_env(monkeypatch)
    token = "file-token-" + "z" * 32
    path = tmp_path / "api-token"
    path.write_text(token + "\n", encoding="utf-8")
    monkeypatch.setenv("XBOW_API_TOKEN_FILE", str(path))
    assert configured_api_token() == token


def test_missing_secret_file_fails_closed(monkeypatch, tmp_path):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN_FILE", str(tmp_path / "missing"))
    with pytest.raises(AuthError) as exc:
        configured_api_token()
    assert exc.value.status_code == 503


def test_conflicting_secret_sources_fail_closed(monkeypatch, tmp_path):
    clear_secret_env(monkeypatch)
    path = tmp_path / "api-token"
    path.write_text("f" * 32, encoding="utf-8")
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 32)
    monkeypatch.setenv("XBOW_API_TOKEN_FILE", str(path))
    with pytest.raises(AuthError) as exc:
        configured_api_token()
    assert exc.value.status_code == 503


def test_whitespace_inside_token_is_rejected(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 20 + " " + "b" * 20)
    with pytest.raises(AuthError):
        configured_api_token()


def test_missing_client_token_is_unauthorized(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 32)
    with pytest.raises(AuthError) as exc:
        require_api_token(request())
    assert exc.value.status_code == 401


def test_wrong_client_token_is_forbidden(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 32)
    with pytest.raises(AuthError) as exc:
        require_api_token(request({"Authorization": "Bearer " + "b" * 32}))
    assert exc.value.status_code == 403


def test_bearer_token_is_accepted(monkeypatch):
    clear_secret_env(monkeypatch)
    token = "correct-token-" + "x" * 32
    monkeypatch.setenv("XBOW_API_TOKEN", token)
    require_api_token(request({"Authorization": f"Bearer {token}"}))


def test_x_api_key_fallback_is_accepted(monkeypatch):
    clear_secret_env(monkeypatch)
    token = "mobile-token-" + "y" * 32
    monkeypatch.setenv("XBOW_API_TOKEN", token)
    require_api_token(request({"X-API-Key": token}))


def _request_for_path(path: str, headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": raw,
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1234),
            "scheme": "http",
        }
    )


def test_control_api_middleware_blocks_missing_token(monkeypatch):
    clear_secret_env(monkeypatch)
    monkeypatch.setenv("XBOW_API_TOKEN", "a" * 32)
    called = False

    async def call_next(_request):
        nonlocal called
        called = True
        return None

    response = asyncio.run(
        authenticate_control_api(_request_for_path("/api/campaigns"), call_next)
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert called is False


def test_control_api_middleware_accepts_valid_token(monkeypatch):
    clear_secret_env(monkeypatch)
    token = "middleware-token-" + "x" * 32
    monkeypatch.setenv("XBOW_API_TOKEN", token)
    sentinel = object()

    async def call_next(_request):
        return sentinel

    result = asyncio.run(
        authenticate_control_api(
            _request_for_path(
                "/api/campaigns",
                {"Authorization": f"Bearer {token}"},
            ),
            call_next,
        )
    )

    assert result is sentinel


def test_health_endpoints_bypass_control_api_auth(monkeypatch):
    clear_secret_env(monkeypatch)
    called = False
    sentinel = object()

    async def call_next(_request):
        nonlocal called
        called = True
        return sentinel

    result = asyncio.run(
        authenticate_control_api(_request_for_path("/health"), call_next)
    )

    assert result is sentinel
    assert called is True


def test_multiple_authentication_headers_fail_closed(monkeypatch):
    clear_secret_env(monkeypatch)
    token = "ambiguous-token-" + "x" * 32
    monkeypatch.setenv("XBOW_API_TOKEN", token)

    with pytest.raises(AuthError) as exc:
        require_api_token(
            request(
                {
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token,
                }
            )
        )

    assert exc.value.status_code == 400


def test_malformed_authorization_does_not_fall_back_to_api_key(monkeypatch):
    clear_secret_env(monkeypatch)
    token = "fallback-token-" + "y" * 32
    monkeypatch.setenv("XBOW_API_TOKEN", token)

    with pytest.raises(AuthError) as exc:
        require_api_token(
            request(
                {
                    "Authorization": "Basic ignored",
                    "X-API-Key": token,
                }
            )
        )

    assert exc.value.status_code == 400


def test_symlinked_secret_file_fails_closed(monkeypatch, tmp_path):
    clear_secret_env(monkeypatch)
    target = tmp_path / "real-token"
    target.write_text("z" * 32, encoding="utf-8")
    link = tmp_path / "api-token"
    link.symlink_to(target)
    monkeypatch.setenv("XBOW_API_TOKEN_FILE", str(link))

    with pytest.raises(AuthError) as exc:
        configured_api_token()

    assert exc.value.status_code == 503


def test_oversized_secret_file_fails_closed(monkeypatch, tmp_path):
    clear_secret_env(monkeypatch)
    path = tmp_path / "api-token"
    path.write_text("z" * 5000, encoding="utf-8")
    monkeypatch.setenv("XBOW_API_TOKEN_FILE", str(path))

    with pytest.raises(AuthError) as exc:
        configured_api_token()

    assert exc.value.status_code == 503
