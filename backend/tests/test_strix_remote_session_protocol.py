import json

import pytest

from app.strix_remote_session_protocol import (
    RPC_SCHEMA,
    ReplayGuard,
    RpcAuthError,
    RpcProtocolError,
    canonical_json_bytes,
    sign_request,
    validate_contract_hash,
    validate_session_id,
    verify_request,
)


def test_canonical_json_is_deterministic():
    first = canonical_json_bytes({"b": 2, "a": [3, 1]})
    second = canonical_json_bytes({"a": [3, 1], "b": 2})

    assert first == second
    assert first == b'{"a":[3,1],"b":2}'


def test_hmac_signature_round_trip_and_replay_rejection():
    secret = "runner-rpc-fixture-secret-32-bytes"
    body = canonical_json_bytes(
        {
            "schema": RPC_SCHEMA,
            "contract_hash": "a" * 64,
            "client_request_id": "b" * 32,
        }
    )
    timestamp = 1_800_000_000
    nonce = "c" * 32
    signature = sign_request(
        secret,
        method="POST",
        path="/v1/session/create",
        body=body,
        timestamp=timestamp,
        nonce=nonce,
    )
    guard = ReplayGuard(max_entries=8, ttl_seconds=60)

    verify_request(
        secret,
        method="POST",
        path="/v1/session/create",
        body=body,
        timestamp=str(timestamp),
        nonce=nonce,
        signature=signature,
        now=timestamp,
        replay_guard=guard,
    )

    with pytest.raises(RpcAuthError, match="replay"):
        verify_request(
            secret,
            method="POST",
            path="/v1/session/create",
            body=body,
            timestamp=str(timestamp),
            nonce=nonce,
            signature=signature,
            now=timestamp,
            replay_guard=guard,
        )


def test_signature_binds_method_path_and_body():
    secret = "runner-rpc-fixture-secret-32-bytes"
    body = b'{"schema":"strix-remote-session-v1"}'
    signature = sign_request(
        secret,
        method="POST",
        path="/v1/session/create",
        body=body,
        timestamp=100,
        nonce="d" * 32,
    )

    for method, path, changed_body in (
        ("GET", "/v1/session/create", body),
        ("POST", "/v1/session/delete", body),
        ("POST", "/v1/session/create", b"{}"),
    ):
        with pytest.raises(RpcAuthError, match="signature"):
            verify_request(
                secret,
                method=method,
                path=path,
                body=changed_body,
                timestamp="100",
                nonce="d" * 32,
                signature=signature,
                now=100,
                replay_guard=ReplayGuard(),
            )


@pytest.mark.parametrize("timestamp", ["", "abc", "99.5"])
def test_invalid_timestamp_is_rejected(timestamp):
    with pytest.raises(RpcAuthError, match="timestamp"):
        verify_request(
            "runner-rpc-fixture-secret-32-bytes",
            method="POST",
            path="/v1/session/create",
            body=b"{}",
            timestamp=timestamp,
            nonce="e" * 32,
            signature="0" * 64,
            now=100,
            replay_guard=ReplayGuard(),
        )


def test_stale_timestamp_is_rejected():
    secret = "runner-rpc-fixture-secret-32-bytes"
    body = b"{}"
    signature = sign_request(
        secret,
        method="POST",
        path="/v1/session/create",
        body=body,
        timestamp=100,
        nonce="f" * 32,
    )

    with pytest.raises(RpcAuthError, match="timestamp"):
        verify_request(
            secret,
            method="POST",
            path="/v1/session/create",
            body=body,
            timestamp="100",
            nonce="f" * 32,
            signature=signature,
            now=200,
            replay_guard=ReplayGuard(ttl_seconds=30),
        )


def test_bad_nonce_and_signature_are_rejected():
    secret = "runner-rpc-fixture-secret-32-bytes"

    with pytest.raises(RpcAuthError, match="nonce"):
        verify_request(
            secret,
            method="POST",
            path="/v1/session/create",
            body=b"{}",
            timestamp="100",
            nonce="../bad",
            signature="0" * 64,
            now=100,
            replay_guard=ReplayGuard(),
        )

    with pytest.raises(RpcAuthError, match="signature"):
        verify_request(
            secret,
            method="POST",
            path="/v1/session/create",
            body=b"{}",
            timestamp="100",
            nonce="a" * 32,
            signature="0" * 64,
            now=100,
            replay_guard=ReplayGuard(),
        )


def test_short_secret_is_rejected():
    with pytest.raises(RpcAuthError, match="secret"):
        sign_request(
            "short",
            method="POST",
            path="/v1/session/create",
            body=b"{}",
            timestamp=100,
            nonce="a" * 32,
        )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 63,
        "A" * 64,
        "g" * 64,
        "../" + "a" * 64,
    ],
)
def test_contract_hash_validation_is_strict(value):
    with pytest.raises(RpcProtocolError, match="contract hash"):
        validate_contract_hash(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 31,
        "A" * 32,
        "z" * 32,
        "../" + "a" * 32,
    ],
)
def test_session_id_validation_is_strict(value):
    with pytest.raises(RpcProtocolError, match="session id"):
        validate_session_id(value)


def test_protocol_schema_is_stable():
    assert RPC_SCHEMA == "strix-remote-session-v1"
    assert json.loads(
        canonical_json_bytes({"schema": RPC_SCHEMA}).decode()
    ) == {"schema": RPC_SCHEMA}
