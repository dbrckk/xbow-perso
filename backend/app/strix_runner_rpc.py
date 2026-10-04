from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .strix_runner_attestation import attest_strix_runner


RUNNER_RPC_PROTOCOL = "strix-runner-rpc-v1"
RUNNER_RPC_PORT = 8092
RUNNER_RPC_MAX_BODY_BYTES = 1024 * 1024
RUNNER_RPC_AUTH_WINDOW_SECONDS = 30
RUNNER_RPC_MAX_NONCES = 4096
RUNNER_RPC_SOCKET_TIMEOUT_SECONDS = 5.0
RUNNER_RPC_MAX_CONCURRENT_CONNECTIONS = 16

_MUTATION_PATHS = {
    "/v1/session/create",
    "/v1/session/exec",
    "/v1/session/resolve-port",
    "/v1/session/delete",
}
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RunnerRpcResponse:
    status: int
    json_body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


class RunnerRpcService:
    def __init__(
        self,
        *,
        secret: str | None,
        active_execution: bool,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret if secret else None
        self._active_execution = bool(active_execution)
        self._now = now
        self._nonces: OrderedDict[str, float] = OrderedDict()
        self._nonce_lock = threading.Lock()

    def handle(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> RunnerRpcResponse:
        normalized_method = str(method).upper()
        normalized_headers = {
            str(key).lower(): str(value)
            for key, value in headers.items()
        }

        if normalized_method == "GET" and path == "/healthz":
            return RunnerRpcResponse(
                status=200,
                json_body={
                    "status": "ok",
                    "protocol": RUNNER_RPC_PROTOCOL,
                    "active_execution_enabled": self._active_execution,
                    "implemented_operations": [],
                },
            )

        if normalized_method == "GET" and path == "/readyz":
            if not self._secret:
                return _error(503, "rpc_key_unavailable")
            return RunnerRpcResponse(
                status=200,
                json_body={
                    "status": "ready",
                    "protocol": RUNNER_RPC_PROTOCOL,
                    "active_execution_enabled": self._active_execution,
                    "implemented_operations": [],
                },
            )

        if path not in _MUTATION_PATHS:
            return _error(404, "not_found")
        if normalized_method != "POST":
            return _error(405, "method_not_allowed")

        auth_error = self._authenticate(
            method=normalized_method,
            path=path,
            headers=normalized_headers,
            body=body,
        )
        if auth_error is not None:
            return auth_error

        if len(body) > RUNNER_RPC_MAX_BODY_BYTES:
            return _error(413, "request_too_large")
        content_type = normalized_headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            return _error(415, "unsupported_media_type")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return _error(400, "invalid_request")
        if not isinstance(payload, dict):
            return _error(400, "invalid_request")
        if not _validate_operation_payload(path, payload):
            return _error(400, "invalid_request")

        if not self._active_execution:
            return _error(503, "active_execution_disabled")
        return _error(501, "rpc_operation_not_implemented")

    def _authenticate(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> RunnerRpcResponse | None:
        if not self._secret:
            return _error(503, "rpc_key_unavailable")

        timestamp_raw = headers.get("x-xbow-runner-timestamp")
        nonce = headers.get("x-xbow-runner-nonce")
        signature = headers.get("x-xbow-runner-signature")
        if not timestamp_raw or not nonce or not signature:
            return _error(401, "authentication_required")

        try:
            timestamp = int(timestamp_raw)
        except ValueError:
            return _error(401, "authentication_required")
        if not _NONCE_RE.fullmatch(nonce):
            return _error(401, "authentication_required")
        if not _SIGNATURE_RE.fullmatch(signature):
            return _error(401, "authentication_required")

        now = float(self._now())
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        if abs(now - timestamp) > RUNNER_RPC_AUTH_WINDOW_SECONDS:
            return _error(401, "timestamp_out_of_window")

        expected = sign_runner_rpc_request(
            method=method,
            path=path,
            body=body,
            secret=self._secret,
            timestamp=timestamp,
            nonce=nonce,
        )
        if not hmac.compare_digest(signature, expected):
            return _error(401, "signature_mismatch")

        with self._nonce_lock:
            self._prune_nonces(now)
            if nonce in self._nonces:
                return _error(409, "replay_detected")
            if len(self._nonces) >= RUNNER_RPC_MAX_NONCES:
                return _error(503, "replay_cache_saturated")
            self._nonces[nonce] = now
            self._nonces.move_to_end(nonce)
        return None

    def _prune_nonces(self, now: float) -> None:
        cutoff = now - RUNNER_RPC_AUTH_WINDOW_SECONDS
        while self._nonces:
            _nonce, seen_at = next(iter(self._nonces.items()))
            if seen_at >= cutoff:
                break
            self._nonces.popitem(last=False)


def sign_runner_rpc_request(
    *,
    method: str,
    path: str,
    body: bytes,
    secret: str,
    timestamp: int,
    nonce: str,
) -> str:
    if not secret or len(secret.encode("utf-8")) > 4096:
        raise ValueError("runner RPC secret is invalid")
    body_digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        (
            RUNNER_RPC_PROTOCOL,
            str(method).upper(),
            str(path),
            str(int(timestamp)),
            str(nonce),
            body_digest,
        )
    ).encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()


def configure_runner_rpc_socket(connection: Any) -> None:
    connection.settimeout(RUNNER_RPC_SOCKET_TIMEOUT_SECONDS)


def _error(status: int, code: str) -> RunnerRpcResponse:
    return RunnerRpcResponse(
        status=status,
        json_body={
            "status": "error",
            "error": code,
            "protocol": RUNNER_RPC_PROTOCOL,
        },
    )


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _valid_port(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 1 <= value <= 65535
    )


def _exact_keys(payload: dict[str, Any], expected: set[str]) -> bool:
    return set(payload) == expected


def _valid_common(payload: dict[str, Any]) -> bool:
    return (
        payload.get("schema") == RUNNER_RPC_PROTOCOL
        and _valid_id(payload.get("request_id"))
    )


def _validate_operation_payload(path: str, payload: dict[str, Any]) -> bool:
    if not _valid_common(payload):
        return False

    if path == "/v1/session/create":
        if not _exact_keys(
            payload,
            {
                "schema",
                "request_id",
                "image",
                "exposed_ports",
                "manifest_digest",
            },
        ):
            return False
        image = payload.get("image")
        ports = payload.get("exposed_ports")
        if (
            not isinstance(image, str)
            or not 1 <= len(image) <= 512
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in image)
            or not isinstance(ports, list)
            or not 0 <= len(ports) <= 16
            or any(not _valid_port(port) for port in ports)
            or len(set(ports)) != len(ports)
            or not _valid_digest(payload.get("manifest_digest"))
        ):
            return False
        return True

    if path == "/v1/session/exec":
        if not _exact_keys(
            payload,
            {
                "schema",
                "request_id",
                "session_id",
                "argv",
                "timeout_seconds",
            },
        ):
            return False
        argv = payload.get("argv")
        timeout = payload.get("timeout_seconds")
        if not _valid_id(payload.get("session_id")):
            return False
        if (
            not isinstance(argv, list)
            or not 1 <= len(argv) <= 64
            or any(
                not isinstance(arg, str)
                or not 1 <= len(arg) <= 4096
                or any(
                    ord(char) < 0x20 and char not in "\t"
                    or ord(char) == 0x7F
                    for char in arg
                )
                for arg in argv
            )
            or sum(len(arg.encode("utf-8")) for arg in argv) > 16 * 1024
        ):
            return False
        if (
            not isinstance(timeout, int | float)
            or isinstance(timeout, bool)
            or not math.isfinite(float(timeout))
            or not 0.1 <= float(timeout) <= 600.0
        ):
            return False
        return True

    if path == "/v1/session/resolve-port":
        return (
            _exact_keys(
                payload,
                {
                    "schema",
                    "request_id",
                    "session_id",
                    "port",
                },
            )
            and _valid_id(payload.get("session_id"))
            and _valid_port(payload.get("port"))
        )

    if path == "/v1/session/delete":
        return (
            _exact_keys(
                payload,
                {
                    "schema",
                    "request_id",
                    "session_id",
                },
            )
            and _valid_id(payload.get("session_id"))
        )

    return False


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        *args: Any,
        max_concurrent_connections: int = RUNNER_RPC_MAX_CONCURRENT_CONNECTIONS,
        **kwargs: Any,
    ) -> None:
        if max_concurrent_connections < 1:
            raise ValueError("max_concurrent_connections must be positive")
        super().__init__(*args, **kwargs)
        self._request_slots = threading.BoundedSemaphore(
            max_concurrent_connections
        )

    def process_request(
        self,
        request: Any,
        client_address: Any,
    ) -> None:
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(
        self,
        request: Any,
        client_address: Any,
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class _RunnerRpcHttpHandler(BaseHTTPRequestHandler):
    server_version = "xbow-strix-runner-rpc/1"

    def setup(self) -> None:
        configure_runner_rpc_socket(self.request)
        super().setup()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def _dispatch(self) -> None:
        service = getattr(self.server, "rpc_service", None)
        if not isinstance(service, RunnerRpcService):
            self._write(_error(503, "rpc_service_unavailable"))
            return

        body = b""
        if self.command == "POST":
            if self.headers.get("Transfer-Encoding"):
                self._write(_error(400, "invalid_request"))
                return
            length_raw = self.headers.get("Content-Length")
            try:
                length = int(length_raw or "0")
            except ValueError:
                self._write(_error(400, "invalid_request"))
                return
            if length < 0:
                self._write(_error(400, "invalid_request"))
                return
            if length > RUNNER_RPC_MAX_BODY_BYTES:
                self._write(_error(413, "request_too_large"))
                return
            body = self.rfile.read(length)

        result = service.handle(
            method=self.command,
            path=self.path,
            headers={key: value for key, value in self.headers.items()},
            body=body,
        )
        self._write(result)

    def _write(self, result: RunnerRpcResponse) -> None:
        payload = json.dumps(
            result.json_body,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(result.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for name, value in result.headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _rpc_secret_from_env() -> str | None:
    secret = os.getenv("XBOW_STRIX_RUNNER_RPC_HMAC_KEY", "")
    if not secret:
        return None
    if len(secret.encode("utf-8")) > 4096:
        raise RuntimeError("Strix runner RPC key is invalid")
    return secret


def serve() -> None:
    attestation = attest_strix_runner()
    if attestation.get("active_execution_enabled") is not False:
        raise RuntimeError("Strix runner attestation did not fail closed")

    service = RunnerRpcService(
        secret=_rpc_secret_from_env(),
        active_execution=False,
    )
    server = BoundedThreadingHTTPServer(
        ("0.0.0.0", RUNNER_RPC_PORT),
        _RunnerRpcHttpHandler,
    )
    server.daemon_threads = True
    setattr(server, "rpc_service", service)
    server.serve_forever(poll_interval=0.5)


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if not args.serve:
        raise RuntimeError("only --serve is supported")
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
