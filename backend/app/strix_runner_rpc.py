from __future__ import annotations

import argparse
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock
from typing import Any

from .strix_remote_session_protocol import (
    RPC_SCHEMA,
    ReplayGuard,
    RpcAuthError,
    RpcProtocolError,
    canonical_json_bytes,
    sign_request,
    validate_client_request_id,
    validate_contract_hash,
    validate_session_id,
    verify_request,
)
from .strix_runner_attestation import attest_strix_runner


RPC_PORT = 8092
_MAX_BODY_BYTES = 64 * 1024
_DISABLED_OPERATIONS = {
    "exec",
    "write",
    "resolve_exposed_port",
}


class RunnerRpcError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 409):
        self.status_code = status_code
        super().__init__(message)


class RunnerSessionState:
    def __init__(self, *, max_sessions: int = 32) -> None:
        if not 1 <= int(max_sessions) <= 256:
            raise ValueError("max_sessions must be between 1 and 256")
        self.max_sessions = int(max_sessions)
        self._sessions: dict[str, dict[str, str]] = {}
        self._request_to_session: dict[str, str] = {}
        self._lock = Lock()

    @staticmethod
    def _capabilities() -> dict[str, bool]:
        return {
            "exec": False,
            "write": False,
            "resolve_exposed_port": False,
        }

    def create_session(
        self,
        *,
        contract_hash: str,
        client_request_id: str,
    ) -> dict[str, Any]:
        normalized_contract = validate_contract_hash(contract_hash)
        normalized_request_id = validate_client_request_id(
            client_request_id
        )
        with self._lock:
            existing_id = self._request_to_session.get(
                normalized_request_id
            )
            if existing_id is not None:
                existing = self._sessions.get(existing_id)
                if (
                    existing is None
                    or existing["contract_hash"] != normalized_contract
                ):
                    raise RunnerRpcError(
                        "RPC client request id cannot change contract"
                    )
                return self._session_response(existing_id, existing)

            if len(self._sessions) >= self.max_sessions:
                raise RunnerRpcError(
                    "RPC session capacity exceeded",
                    status_code=503,
                )

            session_id = secrets.token_hex(16)
            while session_id in self._sessions:
                session_id = secrets.token_hex(16)
            record = {
                "contract_hash": normalized_contract,
                "client_request_id": normalized_request_id,
            }
            self._sessions[session_id] = record
            self._request_to_session[normalized_request_id] = session_id
            return self._session_response(session_id, record)

    def _session_response(
        self,
        session_id: str,
        record: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "schema": RPC_SCHEMA,
            "session_id": session_id,
            "contract_hash": record["contract_hash"],
            "state": "created",
            "capabilities": self._capabilities(),
        }

    def delete_session(self, session_id: str) -> bool:
        normalized = validate_session_id(session_id)
        with self._lock:
            record = self._sessions.pop(normalized, None)
            if record is None:
                return False
            self._request_to_session.pop(
                record["client_request_id"],
                None,
            )
            return True

    def require_operation(
        self,
        session_id: str,
        operation: str,
    ) -> None:
        normalized = validate_session_id(session_id)
        with self._lock:
            if normalized not in self._sessions:
                raise RunnerRpcError(
                    "RPC unknown session",
                    status_code=404,
                )
        if operation in _DISABLED_OPERATIONS:
            raise RunnerRpcError(
                f"RPC operation disabled: {operation}",
                status_code=503,
            )
        raise RunnerRpcError(
            "RPC operation is unsupported",
            status_code=404,
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            session_count = len(self._sessions)
        return {
            "schema": RPC_SCHEMA,
            "session_count": session_count,
            "max_sessions": self.max_sessions,
            "active_execution_enabled": False,
            "capabilities": self._capabilities(),
        }


def _rpc_secret() -> str:
    secret = os.getenv("XBOW_STRIX_RUNNER_RPC_KEY", "")
    encoded = secret.encode("utf-8")
    if not 16 <= len(encoded) <= 4096:
        raise RunnerRpcError(
            "Strix runner RPC key is unavailable or invalid",
            status_code=503,
        )
    return secret


def _strict_object(
    payload: Any,
    *,
    allowed_keys: set[str],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RpcProtocolError("RPC body must be a JSON object")
    unknown = set(payload) - allowed_keys
    if unknown:
        raise RpcProtocolError("RPC body contains unsupported fields")
    if payload.get("schema") != RPC_SCHEMA:
        raise RpcProtocolError("RPC schema mismatch")
    return payload


class _RunnerRpcServer(HTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        *,
        state: RunnerSessionState,
        secret: str,
        attestation: dict[str, Any],
    ) -> None:
        super().__init__(address, _RunnerRpcHandler)
        self.rpc_state = state
        self.rpc_secret = secret
        self.rpc_attestation = attestation
        self.replay_guard = ReplayGuard(
            max_entries=4096,
            ttl_seconds=30,
        )


class _RunnerRpcHandler(BaseHTTPRequestHandler):
    server_version = "xbow-strix-runner-rpc"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def rpc_server(self) -> _RunnerRpcServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
    ) -> None:
        body = canonical_json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _read_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding"):
            raise RpcProtocolError(
                "RPC transfer encoding is unsupported"
            )
        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";", 1)[0].strip().lower() != (
            "application/json"
        ):
            raise RpcProtocolError("RPC content type must be application/json")
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdigit():
            raise RpcProtocolError("RPC content length is invalid")
        length = int(raw_length)
        if not 0 <= length <= _MAX_BODY_BYTES:
            raise RpcProtocolError("RPC body exceeds size limit")
        body = self.rfile.read(length)
        if len(body) != length:
            raise RpcProtocolError("RPC body is incomplete")
        return body

    def _verify_auth(self, body: bytes) -> None:
        verify_request(
            self.rpc_server.rpc_secret,
            method=self.command,
            path=self.path,
            body=body,
            timestamp=self.headers.get(
                "X-Xbow-Rpc-Timestamp",
                "",
            ),
            nonce=self.headers.get("X-Xbow-Rpc-Nonce", ""),
            signature=self.headers.get(
                "X-Xbow-Rpc-Signature",
                "",
            ),
            replay_guard=self.rpc_server.replay_guard,
        )

    @staticmethod
    def _decode_json(body: bytes) -> Any:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RpcProtocolError("RPC JSON body is invalid") from exc

    def do_GET(self) -> None:
        if self.path not in {"/healthz", "/readyz"}:
            self._send_json(404, {"detail": "not found"})
            return
        snapshot = self.rpc_server.rpc_state.snapshot()
        self._send_json(
            200,
            {
                "status": "ready",
                **snapshot,
                "strix_version": self.rpc_server.rpc_attestation[
                    "version"
                ],
                "source_commit": self.rpc_server.rpc_attestation[
                    "source_commit"
                ],
            },
        )

    def do_POST(self) -> None:
        try:
            body = self._read_body()
            self._verify_auth(body)
            payload = self._decode_json(body)
            response = self._dispatch_post(payload)
            self._send_json(200, response)
        except RpcAuthError:
            self._send_json(
                401,
                {"detail": "RPC authentication failed"},
            )
        except RpcProtocolError as exc:
            self._send_json(400, {"detail": str(exc)})
        except RunnerRpcError as exc:
            self._send_json(
                exc.status_code,
                {"detail": str(exc)},
            )

    def _dispatch_post(self, payload: Any) -> dict[str, Any]:
        if self.path == "/v1/session/create":
            data = _strict_object(
                payload,
                allowed_keys={
                    "schema",
                    "contract_hash",
                    "client_request_id",
                },
            )
            return self.rpc_server.rpc_state.create_session(
                contract_hash=str(data.get("contract_hash") or ""),
                client_request_id=str(
                    data.get("client_request_id") or ""
                ),
            )

        if self.path == "/v1/session/delete":
            data = _strict_object(
                payload,
                allowed_keys={"schema", "session_id"},
            )
            session_id = str(data.get("session_id") or "")
            return {
                "schema": RPC_SCHEMA,
                "deleted": self.rpc_server.rpc_state.delete_session(
                    session_id
                ),
            }

        operation_by_path = {
            "/v1/session/exec": "exec",
            "/v1/session/write": "write",
            "/v1/session/resolve-port": "resolve_exposed_port",
        }
        operation = operation_by_path.get(self.path)
        if operation is not None:
            data = _strict_object(
                payload,
                allowed_keys={"schema", "session_id"},
            )
            self.rpc_server.rpc_state.require_operation(
                str(data.get("session_id") or ""),
                operation,
            )
            raise AssertionError("disabled RPC operation returned")

        raise RunnerRpcError(
            "RPC endpoint is unsupported",
            status_code=404,
        )


def serve() -> None:
    attestation = attest_strix_runner()
    secret = _rpc_secret()
    state = RunnerSessionState()
    server = _RunnerRpcServer(
        ("0.0.0.0", RPC_PORT),
        state=state,
        secret=secret,
        attestation=attestation,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


def _signed_post(
    *,
    base_url: str,
    path: str,
    payload: dict[str, Any],
    secret: str,
) -> tuple[int, dict[str, Any]]:
    body = canonical_json_bytes(payload)
    timestamp = int(time.time())
    nonce = secrets.token_hex(16)
    signature = sign_request(
        secret,
        method="POST",
        path=path,
        body=body,
        timestamp=timestamp,
        nonce=nonce,
    )
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Xbow-Rpc-Timestamp": str(timestamp),
            "X-Xbow-Rpc-Nonce": nonce,
            "X-Xbow-Rpc-Signature": signature,
        },
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({})
    )
    try:
        with opener.open(request, timeout=3) as response:
            raw = response.read(_MAX_BODY_BYTES + 1)
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read(_MAX_BODY_BYTES + 1)
        status = int(exc.code)
    if len(raw) > _MAX_BODY_BYTES:
        raise RunnerRpcError("RPC probe response exceeds size limit")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerRpcError("RPC probe response is invalid") from exc
    if not isinstance(decoded, dict):
        raise RunnerRpcError("RPC probe response is invalid")
    return status, decoded


def probe() -> None:
    secret = _rpc_secret()
    base_url = f"http://127.0.0.1:{RPC_PORT}"
    client_request_id = secrets.token_hex(16)
    contract_hash = "0" * 64

    create_status, created = _signed_post(
        base_url=base_url,
        path="/v1/session/create",
        payload={
            "schema": RPC_SCHEMA,
            "contract_hash": contract_hash,
            "client_request_id": client_request_id,
        },
        secret=secret,
    )
    if create_status != 200:
        raise RunnerRpcError("RPC probe could not create session")
    session_id = validate_session_id(
        str(created.get("session_id") or "")
    )

    blocked_status, _blocked = _signed_post(
        base_url=base_url,
        path="/v1/session/exec",
        payload={
            "schema": RPC_SCHEMA,
            "session_id": session_id,
        },
        secret=secret,
    )
    if blocked_status != 503:
        raise RunnerRpcError(
            "RPC probe expected exec to remain disabled"
        )

    delete_status, deleted = _signed_post(
        base_url=base_url,
        path="/v1/session/delete",
        payload={
            "schema": RPC_SCHEMA,
            "session_id": session_id,
        },
        secret=secret,
    )
    if delete_status != 200 or deleted.get("deleted") is not True:
        raise RunnerRpcError("RPC probe could not delete session")

    print("rpc_probe_ok", flush=True)


def _main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--serve", action="store_true")
    mode.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    if args.probe:
        probe()
        return 0
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
