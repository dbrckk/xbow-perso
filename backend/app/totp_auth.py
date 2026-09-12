from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from threading import Lock

import redis
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


def _matching_totp_counter(code: str, *, now: float | None = None) -> int | None:
    if len(code) != 6 or not code.isdigit():
        return None
    secret = configured_totp_secret()
    timestamp = time.time() if now is None else now
    counter = int(timestamp // 30)
    # One adjacent step tolerates small clock skew while remaining bounded.
    for candidate_counter in (counter - 1, counter, counter + 1):
        if hmac.compare_digest(code, _totp(secret, candidate_counter)):
            return candidate_counter
    return None


def verify_totp_code(code: str, *, now: float | None = None) -> bool:
    return _matching_totp_counter(code, now=now) is not None


_replay_lock = Lock()
_used_totp: dict[str, float] = {}


def _replay_backend() -> str:
    backend = os.getenv("XBOW_TOTP_REPLAY_BACKEND", "memory").strip().lower()
    if backend not in {"memory", "redis"}:
        raise AuthError(503, "XBOW_TOTP_REPLAY_BACKEND must be memory or redis")
    return backend


def _consume_memory(key: str, ttl_seconds: int, now: float) -> bool:
    with _replay_lock:
        expired = [item for item, expiry in _used_totp.items() if expiry <= now]
        for item in expired:
            _used_totp.pop(item, None)
        if key in _used_totp:
            return False
        _used_totp[key] = now + ttl_seconds
        return True


def _consume_redis(key: str, ttl_seconds: int) -> bool:
    url = os.getenv("XBOW_TOTP_REPLAY_REDIS_URL", "").strip()
    if not url.startswith(("redis://", "rediss://")):
        raise AuthError(503, "TOTP replay Redis URL is invalid")
    try:
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
        return bool(client.set(key, "1", nx=True, ex=ttl_seconds))
    except redis.RedisError as exc:
        raise AuthError(503, "TOTP replay protection is unavailable") from exc


def consume_totp_code(code: str, *, now: float | None = None) -> bool:
    timestamp = time.time() if now is None else now
    counter = _matching_totp_counter(code, now=timestamp)
    if counter is None:
        return False

    secret = configured_totp_secret()
    fingerprint = hashlib.sha256(
        secret + b":" + str(counter).encode("ascii")
    ).hexdigest()
    ttl_seconds = 90
    key = f"xbow:totp-used:{fingerprint}"
    if _replay_backend() == "memory":
        return _consume_memory(key, ttl_seconds, timestamp)
    return _consume_redis(key, ttl_seconds)


def require_totp_for_mutation(request: Request) -> None:
    if not totp_enabled():
        return
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    code = request.headers.get("x-totp-code", "").strip()
    if not code:
        raise AuthError(401, "TOTP code required")
    if not consume_totp_code(code):
        raise AuthError(403, "Invalid or already used TOTP code")
