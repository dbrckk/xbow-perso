import hashlib
import json
from pathlib import Path

import pytest

from app.strix_runner_rpc import (
    RUNNER_RPC_MIN_SECRET_BYTES,
    RUNNER_RPC_PROTOCOL,
    RunnerRpcService,
    _admission_secret_from_env,
    _rpc_secret_from_env,
    sign_runner_rpc_request,
)
from app.strix_runner_exec_ticket import build_strix_runner_exec_ticket


ROOT = Path(__file__).resolve().parents[2]
SECRET = "fixture-runner-rpc-secret-at-least-32-bytes"
ADMISSION_SECRET = "fixture-runner-admission-secret-at-least-32-bytes"
NOW = 1_800_000_000
NONCE = "0123456789abcdef0123456789abcdef"


def _headers(path: str, body: bytes, *, nonce: str = NONCE):
    signature = sign_runner_rpc_request(
        method="POST",
        path=path,
        body=body,
        secret=SECRET,
        timestamp=NOW,
        nonce=nonce,
    )
    return {
        "x-xbow-runner-timestamp": str(NOW),
        "x-xbow-runner-nonce": nonce,
        "x-xbow-runner-signature": signature,
        "content-type": "application/json",
    }


def _service(
    *,
    secret=SECRET,
    admission_secret=ADMISSION_SECRET,
    active_execution=False,
):
    return RunnerRpcService(
        secret=secret,
        admission_secret=admission_secret,
        active_execution=active_execution,
        now=lambda: NOW,
    )


def _payload(path: str) -> dict:
    if path == "/v1/session/create":
        return {
            "schema": RUNNER_RPC_PROTOCOL,
            "request_id": "req-create-1",
            "image": "ghcr.io/example/sandbox@sha256:" + "a" * 64,
            "exposed_ports": [48080],
            "manifest_digest": "b" * 64,
        }
    if path == "/v1/session/exec":
        argv = [
            "curl",
            "-fsS",
            "http://127.0.0.1:48080/graphql",
        ]
        timeout_seconds = 10.0
        request_id = "req-exec-1"
        session_id = "sess-1"
        canonical = chr(0).join(argv).encode("utf-8")
        descriptor = {
            "schema": "strix-command-admission-v1",
            "contract_hash": "c" * 64,
            "session_id": session_id,
            "request_id": request_id,
            "profile": "bootstrap-v1",
            "executable": "curl",
            "argv_sha256": hashlib.sha256(canonical).hexdigest(),
            "argc": len(argv),
            "argv_bytes": sum(len(arg.encode("utf-8")) for arg in argv),
            "timeout_seconds": timeout_seconds,
            "shell_interpreter_allowed": False,
            "direct_egress_allowed": False,
            "network_scope_enforcement": "broker_required",
            "active_execution_enabled": False,
        }
        return {
            "schema": RUNNER_RPC_PROTOCOL,
            "request_id": request_id,
            "session_id": session_id,
            "argv": argv,
            "timeout_seconds": timeout_seconds,
            "admission": build_strix_runner_exec_ticket(
                descriptor,
                signing_secret=ADMISSION_SECRET,
            ).to_dict(),
        }
    if path == "/v1/session/resolve-port":
        return {
            "schema": RUNNER_RPC_PROTOCOL,
            "request_id": "req-port-1",
            "session_id": "sess-1",
            "port": 48080,
        }
    if path == "/v1/session/delete":
        return {
            "schema": RUNNER_RPC_PROTOCOL,
            "request_id": "req-delete-1",
            "session_id": "sess-1",
        }
    raise AssertionError(path)


def _request(service: RunnerRpcService, path: str, payload: dict):
    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return service.handle(
        method="POST",
        path=path,
        headers=_headers(path, body),
        body=body,
    )


def test_health_is_non_secret_and_execution_stays_disabled():
    result = _service().handle(
        method="GET",
        path="/healthz",
        headers={},
        body=b"",
    )

    assert result.status == 200
    assert result.json_body == {
        "status": "ok",
        "protocol": RUNNER_RPC_PROTOCOL,
        "active_execution_enabled": False,
        "exec_admission_required": True,
        "implemented_operations": [],
    }


def test_ready_requires_rpc_secret():
    result = _service(secret=None).handle(
        method="GET",
        path="/readyz",
        headers={},
        body=b"",
    )

    assert result.status == 503
    assert result.json_body["error"] == "rpc_key_unavailable"


def test_ready_requires_exec_admission_secret():
    result = _service(admission_secret=None).handle(
        method="GET",
        path="/readyz",
        headers={},
        body=b"",
    )

    assert result.status == 503
    assert result.json_body["error"] == "exec_admission_key_unavailable"


@pytest.mark.parametrize(
    "path",
    (
        "/v1/session/create",
        "/v1/session/exec",
        "/v1/session/resolve-port",
        "/v1/session/delete",
    ),
)
def test_authenticated_session_operations_still_fail_closed(path):
    result = _request(_service(), path, _payload(path))

    assert result.status == 503
    assert result.json_body["error"] == "active_execution_disabled"


def test_even_active_flag_cannot_enable_unimplemented_rpc():
    path = "/v1/session/create"
    result = _request(
        _service(active_execution=True),
        path,
        _payload(path),
    )

    assert result.status == 501
    assert result.json_body["error"] == "rpc_operation_not_implemented"


def test_valid_exec_ticket_still_cannot_enable_execution():
    path = "/v1/session/exec"
    result = _request(
        _service(active_execution=True),
        path,
        _payload(path),
    )

    assert result.status == 501
    assert result.json_body["error"] == "rpc_operation_not_implemented"


def test_exec_rejects_tampered_admission_ticket_before_execution_gate():
    path = "/v1/session/exec"
    payload = _payload(path)
    payload["admission"]["signature"] = "0" * 64

    result = _request(_service(), path, payload)

    assert result.status == 403
    assert result.json_body["error"] == "exec_admission_rejected"


def test_exec_rejects_ticket_bound_to_different_argv():
    path = "/v1/session/exec"
    payload = _payload(path)
    payload["argv"] = ["curl", "-I", "http://127.0.0.1:48080/"]

    result = _request(_service(), path, payload)

    assert result.status == 403
    assert result.json_body["error"] == "exec_admission_rejected"


def test_missing_auth_is_rejected_before_payload_processing():
    service = _service()
    result = service.handle(
        method="POST",
        path="/v1/session/create",
        headers={"content-type": "application/json"},
        body=b"not-json",
    )

    assert result.status == 401
    assert result.json_body["error"] == "authentication_required"


def test_signature_covers_body():
    path = "/v1/session/delete"
    original = json.dumps(
        _payload(path),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    tampered = original.replace(b"sess-1", b"sess-2")
    result = _service().handle(
        method="POST",
        path=path,
        headers=_headers(path, original),
        body=tampered,
    )

    assert result.status == 401
    assert result.json_body["error"] == "signature_mismatch"


def test_nonce_replay_is_rejected():
    path = "/v1/session/delete"
    payload = _payload(path)
    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    headers = _headers(path, body)
    service = _service()

    first = service.handle(
        method="POST",
        path=path,
        headers=headers,
        body=body,
    )
    second = service.handle(
        method="POST",
        path=path,
        headers=headers,
        body=body,
    )

    assert first.status == 503
    assert second.status == 409
    assert second.json_body["error"] == "replay_detected"


def test_replay_cache_saturation_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "app.strix_runner_rpc.RUNNER_RPC_MAX_NONCES",
        1,
    )
    path = "/v1/session/delete"
    payload = _payload(path)
    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    service = _service()

    first_headers = _headers(
        path,
        body,
        nonce="00000000000000000000000000000001",
    )
    second_headers = _headers(
        path,
        body,
        nonce="00000000000000000000000000000002",
    )

    first = service.handle(
        method="POST",
        path=path,
        headers=first_headers,
        body=body,
    )
    saturated = service.handle(
        method="POST",
        path=path,
        headers=second_headers,
        body=body,
    )
    replay = service.handle(
        method="POST",
        path=path,
        headers=first_headers,
        body=body,
    )

    assert first.status == 503
    assert saturated.status == 503
    assert saturated.json_body["error"] == "replay_cache_saturated"
    assert replay.status == 409
    assert replay.json_body["error"] == "replay_detected"


def test_stale_timestamp_is_rejected():
    path = "/v1/session/delete"
    body = json.dumps(
        _payload(path),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    stale = NOW - 31
    signature = sign_runner_rpc_request(
        method="POST",
        path=path,
        body=body,
        secret=SECRET,
        timestamp=stale,
        nonce=NONCE,
    )
    result = _service().handle(
        method="POST",
        path=path,
        headers={
            "x-xbow-runner-timestamp": str(stale),
            "x-xbow-runner-nonce": NONCE,
            "x-xbow-runner-signature": signature,
            "content-type": "application/json",
        },
        body=body,
    )

    assert result.status == 401
    assert result.json_body["error"] == "timestamp_out_of_window"


def test_unknown_payload_field_fails_closed():
    path = "/v1/session/delete"
    payload = _payload(path)
    payload["unexpected"] = True
    result = _request(_service(), path, payload)

    assert result.status == 400
    assert result.json_body["error"] == "invalid_request"


@pytest.mark.parametrize(
    ("path", "mutate"),
    (
        (
            "/v1/session/create",
            lambda payload: payload.update(exposed_ports=[0]),
        ),
        (
            "/v1/session/exec",
            lambda payload: payload.update(argv=[]),
        ),
        (
            "/v1/session/resolve-port",
            lambda payload: payload.update(port=65536),
        ),
    ),
)
def test_operation_schema_bounds_are_enforced(path, mutate):
    payload = _payload(path)
    mutate(payload)

    result = _request(_service(), path, payload)

    assert result.status == 400
    assert result.json_body["error"] == "invalid_request"


def test_runner_compose_exposes_rpc_only_internally():
    compose = (ROOT / "docker-compose.yml").read_text()
    block = compose.split("  strix-runner:", 1)[1].split(
        "\n  scanner-worker:",
        1,
    )[0]

    assert 'XBOW_STRIX_ACTIVE_EXECUTION: "false"' in block
    assert "XBOW_STRIX_RUNNER_RPC_HMAC_KEY:" in block
    assert "XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY:" in block
    assert 'networks: [strix-broker]' in block
    assert '"8092"' in block
    assert "\n    ports:" not in block
    assert "app.strix_runner_rpc" in block
    assert "/readyz" in block


def test_ci_waits_for_runner_rpc_readiness():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "runner_ready=0" in workflow
    assert "http://strix-runner:8092/readyz" in workflow
    assert 'if [ "$runner_ready" -ne 1 ]; then' in workflow


def test_runner_image_contains_only_required_runner_modules():
    dockerfile = (ROOT / "backend" / "Dockerfile.strix-runner").read_text()

    assert "COPY app/strix_runner_attestation.py" in dockerfile
    assert "COPY app/strix_runner_rpc.py" in dockerfile
    assert "COPY app/strix_runner_exec_ticket.py" in dockerfile
    assert "COPY app/strix_backend_hook.py" not in dockerfile


def test_runner_rpc_socket_timeout_is_bounded():
    from app.strix_runner_rpc import (
        RUNNER_RPC_SOCKET_TIMEOUT_SECONDS,
        configure_runner_rpc_socket,
    )

    class FakeSocket:
        def __init__(self):
            self.timeout = None

        def settimeout(self, value):
            self.timeout = value

    fake = FakeSocket()

    configure_runner_rpc_socket(fake)

    assert RUNNER_RPC_SOCKET_TIMEOUT_SECONDS == 5.0
    assert fake.timeout == 5.0


def test_runner_rpc_server_rejects_connections_above_cap():
    import threading

    from app.strix_runner_rpc import (
        RUNNER_RPC_MAX_CONCURRENT_CONNECTIONS,
        BoundedThreadingHTTPServer,
    )

    server = object.__new__(BoundedThreadingHTTPServer)
    server._request_slots = threading.BoundedSemaphore(1)
    rejected = []
    server.shutdown_request = rejected.append

    assert RUNNER_RPC_MAX_CONCURRENT_CONNECTIONS == 16
    assert server._request_slots.acquire(blocking=False) is True

    server.process_request("second-request", ("127.0.0.1", 12345))

    assert rejected == ["second-request"]
    server._request_slots.release()


def test_runner_rpc_server_releases_slot_after_request_thread(monkeypatch):
    import threading

    from app.strix_runner_rpc import BoundedThreadingHTTPServer

    server = object.__new__(BoundedThreadingHTTPServer)
    server._request_slots = threading.BoundedSemaphore(1)
    assert server._request_slots.acquire(blocking=False) is True

    def fail_request_thread(_self, _request, _client_address):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(
        "app.strix_runner_rpc.ThreadingHTTPServer.process_request_thread",
        fail_request_thread,
    )

    with pytest.raises(RuntimeError, match="fixture failure"):
        server.process_request_thread("request", ("127.0.0.1", 12345))

    assert server._request_slots.acquire(blocking=False) is True
    server._request_slots.release()


def test_runner_rpc_signer_rejects_short_secret():
    with pytest.raises(ValueError, match="at least 32 bytes"):
        sign_runner_rpc_request(
            method="POST",
            path="/v1/session/delete",
            body=b"{}",
            secret="too-short",
            timestamp=NOW,
            nonce=NONCE,
        )


def test_runner_rpc_service_rejects_short_secret():
    with pytest.raises(ValueError, match="at least 32 bytes"):
        RunnerRpcService(
            secret="too-short",
            admission_secret=ADMISSION_SECRET,
            active_execution=False,
            now=lambda: NOW,
        )


def test_runner_rpc_env_rejects_short_secret(monkeypatch):
    monkeypatch.setenv(
        "XBOW_STRIX_RUNNER_RPC_HMAC_KEY",
        "too-short",
    )

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        _rpc_secret_from_env()


def test_runner_admission_env_rejects_short_secret(monkeypatch):
    monkeypatch.setenv(
        "XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY",
        "too-short",
    )

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        _admission_secret_from_env()


def test_runner_rpc_accepts_exact_minimum_secret_length():
    secret = "x" * RUNNER_RPC_MIN_SECRET_BYTES

    service = RunnerRpcService(
        secret=secret,
        admission_secret=ADMISSION_SECRET,
        active_execution=False,
        now=lambda: NOW,
    )

    assert service.handle(
        method="GET",
        path="/readyz",
        headers={},
        body=b"",
    ).status == 200


def test_runner_rpc_read_deadline_is_absolute(monkeypatch):
    import socket

    from app.strix_runner_rpc import (
        RUNNER_RPC_READ_DEADLINE_SECONDS,
        _RunnerRpcHttpHandler,
    )

    timers = []

    class FakeTimer:
        def __init__(self, interval, callback):
            self.interval = interval
            self.callback = callback
            self.daemon = False
            self.started = False
            self.cancelled = False
            timers.append(self)

        def start(self):
            self.started = True

        def cancel(self):
            self.cancelled = True

    class FakeSocket:
        def __init__(self):
            self.shutdown_mode = None

        def shutdown(self, mode):
            self.shutdown_mode = mode

    monkeypatch.setattr(
        "app.strix_runner_rpc.threading.Timer",
        FakeTimer,
    )
    handler = object.__new__(_RunnerRpcHttpHandler)
    handler.request = FakeSocket()
    handler._read_deadline_timer = None

    handler._start_read_deadline()

    assert RUNNER_RPC_READ_DEADLINE_SECONDS == 10.0
    assert len(timers) == 1
    assert timers[0].interval == 10.0
    assert timers[0].daemon is True
    assert timers[0].started is True

    timers[0].callback()

    assert handler.request.shutdown_mode == socket.SHUT_RDWR

    handler._cancel_read_deadline()

    assert timers[0].cancelled is True
    assert handler._read_deadline_timer is None


def test_runner_rpc_rejects_truncated_body_before_service():
    import io
    from types import SimpleNamespace

    from app.strix_runner_rpc import _RunnerRpcHttpHandler

    handler = object.__new__(_RunnerRpcHttpHandler)
    handler.command = "POST"
    handler.path = "/v1/session/delete"
    handler.headers = {
        "Content-Length": "10",
        "Content-Type": "application/json",
    }
    handler.rfile = io.BytesIO(b"{}")
    handler.server = SimpleNamespace(rpc_service=_service())
    handler._read_deadline_timer = None
    written = []
    handler._write = written.append

    handler._dispatch()

    assert len(written) == 1
    assert written[0].status == 400
    assert written[0].json_body["error"] == "invalid_request"
