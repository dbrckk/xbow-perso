from __future__ import annotations

import hmac
import os

from fastapi import Request


class AuthError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def configured_api_token() -> str:
    """Return the server API token or fail closed when it is unsafe/missing."""
    token = os.getenv("XBOW_API_TOKEN", "").strip()
    if len(token) < 32:
        raise AuthError(503, "API authentication is not configured")
    return token


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
