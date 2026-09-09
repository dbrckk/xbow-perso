from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import Request


class AuthError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _validate_token(token: str) -> str:
    token = token.strip()
    if len(token) < 32 or len(token) > 4096:
        raise AuthError(503, "API authentication is not configured")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in token):
        raise AuthError(503, "API authentication is not configured")
    return token


def configured_api_token() -> str:
    """Return the server API token or fail closed when it is unsafe/missing.

    Prefer XBOW_API_TOKEN_FILE for deployments so the token does not need to be
    present in the process environment. Supplying both sources is rejected to
    prevent ambiguous secret rotation and accidental fallback.
    """
    inline = os.getenv("XBOW_API_TOKEN", "").strip()
    token_file = os.getenv("XBOW_API_TOKEN_FILE", "").strip()
    if inline and token_file:
        raise AuthError(503, "API authentication has conflicting secret sources")
    if token_file:
        path = Path(token_file)
        try:
            if not path.is_file():
                raise OSError("not a regular file")
            token = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise AuthError(503, "API authentication secret file is unavailable") from exc
        return _validate_token(token)
    return _validate_token(inline)


def presented_api_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "").strip()
    if authorization:
        scheme, separator, value = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and value.strip():
            return value.strip()
    fallback = request.headers.get("x-api-key", "").strip()
    return fallback or None


def require_api_token(request: Request) -> None:
    expected = configured_api_token()
    presented = presented_api_token(request)
    if not presented:
        raise AuthError(401, "Authentication required")
    if not hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
        raise AuthError(403, "Invalid API token")
