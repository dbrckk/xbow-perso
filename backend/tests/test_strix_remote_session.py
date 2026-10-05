import asyncio
import inspect
from types import SimpleNamespace

import pytest

from app.strix_remote_session import (
    STRIX_REMOTE_SESSION_SCHEMA,
    PreparedStrixRemoteClient,
    PreparedStrixRemoteSession,
    StrixRemoteSessionBlocked,
    StrixRemoteSessionError,
    prepare_strix_remote_session,
    prepared_remote_session_self_test,
)


def _manifest():
    return SimpleNamespace(
        version=1,
        root="/workspace",
        entries={},
        environment=SimpleNamespace(value={}),
        users=[],
        groups=[],
        extra_path_grants=(),
    )


def _prepared(*, ports=(48080,)):
    return asyncio.run(
        prepare_strix_remote_session(
            image="ghcr.io/example/strix-sandbox:fixture",
            manifest=_manifest(),
            exposed_ports=ports,
            bind_mounts=[],
        )
    )


def test_prepared_backend_returns_client_and_session_without_side_effects():
    client, session = _prepared()

    assert isinstance(client, PreparedStrixRemoteClient)
    assert isinstance(session, PreparedStrixRemoteSession)
    assert session.descriptor.schema == STRIX_REMOTE_SESSION_SCHEMA
    assert session.descriptor.exposed_ports == (48080,)
    assert session.descriptor.manifest_present is True
    assert session.descriptor.manifest_admission_schema == "strix-manifest-admission-v1"
    assert session.descriptor.manifest_admitted is True
    assert len(session.descriptor.manifest_digest) == 64
    assert session.descriptor.manifest_entry_count == 0
    assert session.descriptor.manifest_materialized is False
    assert session.descriptor.bind_mounts_supported is False
    assert session.descriptor.network_io_performed is False
    assert session.descriptor.process_execution_performed is False
    assert session.descriptor.active_execution_enabled is False


def test_exec_plan_matches_pinned_caido_bootstrap_call_shape():
    _client, session = _prepared()
    plan = session.plan_exec(
        "curl",
        "-fsS",
        "-X",
        "POST",
        "-H",
        "Content-Type: application/json",
        "-d",
        '{"query":"mutation LoginAsGuest { loginAsGuest { token { accessToken } } }"}',
        "http://127.0.0.1:48080/graphql",
        timeout=15,
    )

    assert plan.operation == "exec"
    assert plan.executable == "curl"
    assert plan.argc == 9
    assert plan.timeout_seconds == 15.0
    assert len(plan.argv_sha256 or "") == 64
    assert plan.network_io_performed is False
    assert plan.process_execution_performed is False
    assert plan.active_execution_enabled is False


def test_exec_is_async_and_always_fails_closed():
    _client, session = _prepared()

    assert inspect.iscoroutinefunction(session.exec)
    with pytest.raises(StrixRemoteSessionBlocked, match="exec is not enabled"):
        asyncio.run(
            session.exec(
                "curl",
                "-fsS",
                "http://127.0.0.1:48080/graphql",
                timeout=15,
            )
        )


def test_resolve_exposed_port_is_async_and_fails_closed():
    _client, session = _prepared()

    assert inspect.iscoroutinefunction(session.resolve_exposed_port)
    with pytest.raises(StrixRemoteSessionBlocked, match="port resolution"):
        asyncio.run(session.resolve_exposed_port(48080))


def test_resolve_exposed_port_rejects_undeclared_port_before_blocker():
    _client, session = _prepared()

    with pytest.raises(StrixRemoteSessionError, match="was not declared"):
        asyncio.run(session.resolve_exposed_port(8080))


def test_client_delete_is_async_and_fails_closed():
    client, session = _prepared()

    assert inspect.iscoroutinefunction(client.delete)
    with pytest.raises(StrixRemoteSessionBlocked, match="deletion is not enabled"):
        asyncio.run(client.delete(session))


def test_client_delete_rejects_session_mismatch():
    client, _session = _prepared()
    _other_client, other_session = _prepared()

    with pytest.raises(StrixRemoteSessionError, match="session mismatch"):
        client.plan_delete(other_session)


@pytest.mark.parametrize(
    "argv",
    (
        ("sh", "-lc", "printf ok"),
        ("bash", "-c", "id"),
        ("python3", "-c", "print(1)"),
        ("/bin/curl", "-I", "http://127.0.0.1/"),
    ),
)
def test_prepared_exec_plan_rejects_shells_and_executable_paths(argv):
    _client, session = _prepared()

    with pytest.raises(StrixRemoteSessionError, match="executable"):
        session.plan_exec(*argv, timeout=10)


@pytest.mark.parametrize("timeout", (0, -1, 601, float("inf"), float("nan")))
def test_prepared_exec_plan_rejects_invalid_timeout(timeout):
    _client, session = _prepared()

    with pytest.raises(StrixRemoteSessionError, match="timeout"):
        session.plan_exec("curl", "-I", "http://127.0.0.1/", timeout=timeout)


def test_prepared_backend_rejects_bind_mounts():
    with pytest.raises(StrixRemoteSessionError, match="do not support bind mounts"):
        asyncio.run(
            prepare_strix_remote_session(
                image="fixture",
                manifest=_manifest(),
                exposed_ports=(48080,),
                bind_mounts=[
                    {
                        "source": "/tmp/source",
                        "target": "/workspace/repo",
                        "read_only": True,
                    }
                ],
            )
        )


def test_prepared_backend_rejects_duplicate_or_invalid_ports():
    for ports in ((48080, 48080), (0,), (65536,)):
        with pytest.raises(StrixRemoteSessionError):
            _prepared(ports=ports)


def test_self_test_reports_non_executing_interface():
    result = prepared_remote_session_self_test()

    assert result["schema"] == STRIX_REMOTE_SESSION_SCHEMA
    assert result["client_interface_defined"] is True
    assert result["session_interface_defined"] is True
    assert result["exec_signature_compatible"] is True
    assert result["resolve_exposed_port_async"] is True
    assert result["delete_async"] is True
    assert result["manifest_materialized"] is False
    assert result["network_io_performed"] is False
    assert result["process_execution_performed"] is False
    assert result["active_execution_enabled"] is False
