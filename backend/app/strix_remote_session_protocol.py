from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from collections import OrderedDict
from typing import Any


RPC_SCHEMA = "strix-remote-session-v1"
_RPC_DOMAIN = b"xbow:strix-remote-session:v1\x00"
_HEX_32_TO_64 = re.compile(r"^[0-9a-f]{32,64}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class RpcProtocolError(RuntimeError):
    pass


class RpcAuthError(RpcProtocolError):
    pass


def canonical_json_bytes(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RpcProtocolError("RPC JSON payload is invalid") from exc


def _secret_bytes(secret: str) -> bytes:
    value = str(secret).encode("utf-8")
    if not 16 <= len(value) <= 4096:
        raise RpcAuthError("RPC authentication secret is invalid")
    return value


def _validate_method_path(method: str, path: str) -> tuple[str, str]:
    normalized_method = str(method).upper().strip()
    normalized_path = str(path)
    if (
        normalized_method not in {"GET", "POST"}
        or not normalized_path.startswith("/")
        or len(normalized_path) > 512
        or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in normalized_path)
    ):
        raise RpcAuthError("RPC method or path is invalid")
    return normalized_method, normalized_path


def _validate_nonce(nonce: str) -> str:
    value = str(nonce)
    if not _HEX_32_TO_64.fullmatch(value):
        raise RpcAuthError("RPC nonce is invalid")
    return value


def _validate_timestamp(timestamp: str | int) -> int:
    if isinstance(timestamp, bool):
        raise RpcAuthError("RPC timestamp is invalid")
    raw = str(timestamp)
    if not raw or not raw.isdigit():
        raise RpcAuthError("RPC timestamp is invalid")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RpcAuthError("RPC timestamp is invalid") from exc
    if value < 0:
        raise RpcAuthError("RPC timestamp is invalid")
    return value


def _signature_input(
    *,
    method: str,
    path: str,
    body: bytes,
    timestamp: int,
    nonce: str,
) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return _RPC_DOMAIN + (
        f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    ).encode("utf-8")


def sign_request(
    secret: str,
    *,
    method: str,
    path: str,
    body: bytes,
    timestamp: int,
    nonce: str,
) -> str:
    secret_bytes = _secret_bytes(secret)
    normalized_method, normalized_path = _validate_method_path(
        method,
        path,
    )
    normalized_nonce = _validate_nonce(nonce)
    normalized_timestamp = _validate_timestamp(timestamp)
    return hmac.new(
        secret_bytes,
        _signature_input(
            method=normalized_method,
            path=normalized_path,
            body=bytes(body),
            timestamp=normalized_timestamp,
            nonce=normalized_nonce,
        ),
        hashlib.sha256,
    ).hexdigest()


class ReplayGuard:
    def __init__(
        self,
        *,
        max_entries: int = 4096,
        ttl_seconds: int = 30,
    ) -> None:
        if not 1 <= int(max_entries) <= 65536:
            raise ValueError("max_entries must be between 1 and 65536")
        if not 1 <= int(ttl_seconds) <= 300:
            raise ValueError("ttl_seconds must be between 1 and 300")
        self.max_entries = int(max_entries)
        self.ttl_seconds = int(ttl_seconds)
        self._entries: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def consume(self, nonce: str, *, now: float) -> None:
        with self._lock:
            expired = [
                key
                for key, expires_at in self._entries.items()
                if expires_at <= now
            ]
            for key in expired:
                self._entries.pop(key, None)

            if nonce in self._entries:
                raise RpcAuthError("RPC replay detected")
            if len(self._entries) >= self.max_entries:
                raise RpcAuthError("RPC replay guard capacity exceeded")

            self._entries[nonce] = now + self.ttl_seconds
            self._entries.move_to_end(nonce)


def verify_request(
    secret: str,
    *,
    method: str,
    path: str,
    body: bytes,
    timestamp: str | int,
    nonce: str,
    signature: str,
    replay_guard: ReplayGuard,
    now: float | None = None,
) -> None:
    secret_bytes = _secret_bytes(secret)
    normalized_method, normalized_path = _validate_method_path(
        method,
        path,
    )
    normalized_nonce = _validate_nonce(nonce)
    normalized_timestamp = _validate_timestamp(timestamp)
    current_time = float(time.time() if now is None else now)

    if abs(current_time - normalized_timestamp) > replay_guard.ttl_seconds:
        raise RpcAuthError("RPC timestamp is outside the allowed window")

    supplied_signature = str(signature)
    if not _HEX_64.fullmatch(supplied_signature):
        raise RpcAuthError("RPC signature is invalid")

    expected = hmac.new(
        secret_bytes,
        _signature_input(
            method=normalized_method,
            path=normalized_path,
            body=bytes(body),
            timestamp=normalized_timestamp,
            nonce=normalized_nonce,
        ),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected):
        raise RpcAuthError("RPC signature mismatch")

    replay_guard.consume(normalized_nonce, now=current_time)


def validate_contract_hash(value: str) -> str:
    normalized = str(value)
    if not _HEX_64.fullmatch(normalized):
        raise RpcProtocolError("RPC contract hash is invalid")
    return normalized


def validate_session_id(value: str) -> str:
    normalized = str(value)
    if not re.fullmatch(r"^[0-9a-f]{32}$", normalized):
        raise RpcProtocolError("RPC session id is invalid")
    return normalized


def validate_client_request_id(value: str) -> str:
    normalized = str(value)
    if not re.fullmatch(r"^[0-9a-f]{32}$", normalized):
        raise RpcProtocolError("RPC client request id is invalid")
    return normalized
