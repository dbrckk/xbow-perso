import json
from pathlib import Path

import pytest

from app.strix_runner_rpc import (
    RUNNER_RPC_PROTOCOL,
    RunnerRpcService,
    sign_runner_rpc_request,
)


ROOT = Path(__file__).resolve().parents[2]
SECRET = "fixture-runner-rpc-secret-32-bytes-minimum"
NOW = 1_800_000_000
NONCE = "0123456789abcdef0123456789abcdef"
ATTESTATION = {
    "schema": "strix-runner-attestation-v1",
    "ready": True,
    "version": "1.6.2",
    "source_commit": "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2",
    "binary_sha256": "a" * 64,
    "archive_verified": True,
    "binary_verified": True,
    "docker_socket_present": False,
    "docker_host_configured": False,
    "active_execution_enabled": False,
    "network_mode": "internal_only",
}


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
    active_execution=False,
    attestation=ATTESTATION,
):
    return RunnerRpcService(
        secret=secret,
        active_execution=active_execution,
        attestation=attestation,
        now=lambda: NOW,
    )


def _payload(path: str) -> dict:
    if path == "/v1/session/create":
        return {
            "schema": RUNNER_RPC_PROTOCOL,
            "request_id": "req-create-1",
            "contract_hash": "c" * 64,
            "image": "ghcr.io/example/sandbox@sha256:" + "a" * 64,
            "exposed_ports": [48080],
            "manifest_digest": "b" * 64,
        }
    if path == "/v1/session/exec":
        return {
            "schema": RUNNER_RPC_PROTOCOL,
            "request_id": "req-exec-1",
            "contract_hash": "c" * 64,
            "session_id": "sess-1",
            "argv": ["sh", "-lc", "printf ok"],
            "timeout_seconds": 10.0,
        }
    if path == "/v1/session/resolve-port":
        return {
            "schema": RUNNER_RPC_PROTOCOL,
            "request_id": "req-port-1",
            "contract_hash": "c" * 64,
            "session_id": "sess-1",
            "port": 48080,
        }
    if path == "/v1/session/delete":
        return {
            "schema": RUNNER_RPC_PROTOCOL,
            "request_id": "req-delete-1",
            "contract_hash": "c" * 64,
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


def test_ready_requires_runtime_attestation():
    result = _service(attestation=None).handle(
        method="GET",
        path="/readyz",
        headers={},
        body=b"",
    )

    assert result.status == 503
    assert result.json_body["error"] == "runner_attestation_unavailable"


def test_ready_exposes_exact_runtime_attestation():
    result = _service().handle(
        method="GET",
        path="/readyz",
        headers={},
        body=b"",
    )

    assert result.status == 200
    assert result.json_body["runner_attested"] is True
    assert result.json_body["runner_version"] == "1.6.2"
    assert (
        result.json_body["source_commit"]
        == "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2"
    )
    assert result.json_body["binary_sha256"] == "a" * 64


def test_runner_rpc_rejects_mismatched_runtime_attestation():
    attestation = dict(ATTESTATION)
    attestation["source_commit"] = "0" * 40

    with pytest.raises(ValueError, match="attestation is invalid"):
        _service(attestation=attestation)


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


def test_runner_rpc_rejects_active_execution_mode():
    with pytest.raises(ValueError, match="active execution must remain disabled"):
        _service(active_execution=True)


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
    assert 'networks: [strix-broker]' in block
    assert '"8092"' in block
    assert "\n    ports:" not in block
    assert "app.strix_runner_rpc" in block
    assert "/readyz" in block


def test_ci_waits_for_runner_rpc_readiness():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "runner_ready=0" in workflow
    assert "python -m app.strix_runner_client --check-readiness" in workflow
    assert 'if [ "$runner_ready" -ne 1 ]; then' in workflow


def test_runner_image_contains_only_rpc_and_attestation_modules():
    dockerfile = (ROOT / "backend" / "Dockerfile.strix-runner").read_text()

    assert "COPY app/strix_runner_attestation.py" in dockerfile
    assert "COPY app/strix_runner_rpc.py" in dockerfile
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


def test_runner_rpc_rejects_weak_shared_secret():
    with pytest.raises(ValueError, match="secret is invalid"):
        RunnerRpcService(
            secret="too-short",
            active_execution=False,
            now=lambda: NOW,
        )


def test_runner_rpc_signing_rejects_weak_shared_secret():
    with pytest.raises(ValueError, match="secret is invalid"):
        sign_runner_rpc_request(
            method="POST",
            path="/v1/session/delete",
            body=b"{}",
            secret="too-short",
            timestamp=NOW,
            nonce=NONCE,
        )


@pytest.mark.parametrize(
    "image",
    (
        "ghcr.io/example/sandbox:latest",
        "ghcr.io/example/sandbox:1.0.0",
        "ghcr.io/example/sandbox",
        "ghcr.io/example/sandbox@sha256:" + "A" * 64,
        "ghcr.io/example/sandbox@sha512:" + "a" * 128,
    ),
)
def test_create_requires_immutable_sha256_image_reference(image):
    path = "/v1/session/create"
    payload = _payload(path)
    payload["image"] = image

    result = _request(_service(), path, payload)

    assert result.status == 400
    assert result.json_body["error"] == "invalid_request"


@pytest.mark.parametrize(
    "path",
    (
        "/v1/session/create",
        "/v1/session/exec",
        "/v1/session/resolve-port",
        "/v1/session/delete",
    ),
)
@pytest.mark.parametrize(
    "contract_hash",
    (
        None,
        "not-a-digest",
        "A" * 64,
    ),
)
def test_session_operations_require_canonical_contract_hash(
    path,
    contract_hash,
):
    payload = _payload(path)
    if contract_hash is None:
        payload.pop("contract_hash")
    else:
        payload["contract_hash"] = contract_hash

    result = _request(_service(), path, payload)

    assert result.status == 400
    assert result.json_body["error"] == "invalid_request"
