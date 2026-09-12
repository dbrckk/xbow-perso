from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time

from fastapi import Request

from .auth import AuthError
from .secret_vault import SecretVaultError, get_secret, vault_enabled


def _strict_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise AuthError(503, f"{name} must be a boolean")


def totp_enabled() -> bool:
    return _strict_bool("XBOW_TOTP_ENABLED", False)


def configured_totp_secret() -> bytes:
    inline = os.getenv("XBOW_TOTP_SECRET", "").strip()
    try:
        use_vault = vault_enabled()
    except SecretVaultError as exc:
        raise AuthError(503, "TOTP vault configuration is invalid") from exc

    if use_vault:
        if inline:
            raise AuthError(503, "TOTP has conflicting legacy secret sources")
        try:
            inline = get_secret("totp_secret")
        except SecretVaultError as exc:
            raise AuthError(503, "TOTP vault secret is unavailable") from exc

    if not inline:
        raise AuthError(503, "TOTP secret is not configured")

    normalized = inline.replace(" ", "").upper()
    if not 16 <= len(normalized) <= 128:
        raise AuthError(503, "TOTP secret is not configured")
    try:
        secret = base64.b32decode(normalized, casefold=True)
    except Exception as exc:
        raise AuthError(503, "TOTP secret is invalid") from exc
    if len(secret) < 10 or len(secret) > 64:
        raise AuthError(503, "TOTP secret is invalid")
    return secret


def _totp(secret: bytes, counter: int, digits: int = 6) -> str:
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def verify_totp_code(code: str, *, now: float | None = None) -> bool:
    if len(code) != 6 or not code.isdigit():
        return False
    secret = configured_totp_secret()
    timestamp = time.time() if now is None else now
    counter = int(timestamp // 30)
    # One adjacent step tolerates small clock skew while remaining bounded.
    candidates = (_totp(secret, counter - 1), _totp(secret, counter), _totp(secret, counter + 1))
    return any(hmac.compare_digest(code, candidate) for candidate in candidates)


def require_totp_for_mutation(request: Request) -> None:
    if not totp_enabled():
        return
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    code = request.headers.get("x-totp-code", "").strip()
    if not code:
        raise AuthError(401, "TOTP code required")
    if not verify_totp_code(code):
        raise AuthError(403, "Invalid TOTP code")
