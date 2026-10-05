import hashlib

import pytest

from app.strix_runner_exec_ticket import (
    StrixRunnerExecTicketError,
    build_strix_runner_exec_ticket,
    validate_strix_runner_exec_ticket_secret,
    verify_strix_runner_exec_ticket,
)


SECRET = "runner-exec-ticket-secret-at-least-32-bytes"


def _descriptor(*, argv=None, timeout_seconds=10.0):
    argv = list(argv or ["curl", "-fsS", "http://127.0.0.1:48080/graphql"])
    canonical = "\x00".join(argv).encode("utf-8")
    return {
        "schema": "strix-command-admission-v1",
        "contract_hash": "a" * 64,
        "session_id": "sess-1",
        "request_id": "req-1",
        "profile": "bootstrap-v1",
        "executable": argv[0],
        "argv_sha256": hashlib.sha256(canonical).hexdigest(),
        "argc": len(argv),
        "argv_bytes": sum(len(arg.encode("utf-8")) for arg in argv),
        "timeout_seconds": timeout_seconds,
        "shell_interpreter_allowed": False,
        "direct_egress_allowed": False,
        "network_scope_enforcement": "broker_required",
        "active_execution_enabled": False,
    }


def test_exec_ticket_round_trip_binds_request_identity_and_argv():
    argv = ["curl", "-fsS", "http://127.0.0.1:48080/graphql"]
    ticket = build_strix_runner_exec_ticket(
        _descriptor(argv=argv),
        signing_secret=SECRET,
    )

    verified = verify_strix_runner_exec_ticket(
        ticket.to_dict(),
        session_id="sess-1",
        request_id="req-1",
        argv=argv,
        timeout_seconds=10.0,
        verification_secret=SECRET,
    )

    assert verified.contract_hash == "a" * 64
    assert verified.executable == "curl"
    assert verified.direct_egress_allowed is False
    assert verified.network_scope_enforcement == "broker_required"
    assert verified.active_execution_enabled is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("shell_interpreter_allowed", True),
        ("direct_egress_allowed", True),
        ("network_scope_enforcement", "direct"),
        ("active_execution_enabled", True),
    ),
)
def test_exec_ticket_rejects_safety_invariant_drift(field, value):
    descriptor = _descriptor()
    descriptor[field] = value

    with pytest.raises(StrixRunnerExecTicketError, match="safety invariants"):
        build_strix_runner_exec_ticket(
            descriptor,
            signing_secret=SECRET,
        )


@pytest.mark.parametrize("executable", ("sh", "bash", "python3", "/bin/curl"))
def test_exec_ticket_rejects_shells_and_executable_paths(executable):
    descriptor = _descriptor()
    descriptor["executable"] = executable

    with pytest.raises(StrixRunnerExecTicketError, match="executable"):
        build_strix_runner_exec_ticket(
            descriptor,
            signing_secret=SECRET,
        )


def test_exec_ticket_rejects_wrong_verification_key():
    ticket = build_strix_runner_exec_ticket(
        _descriptor(),
        signing_secret=SECRET,
    )

    with pytest.raises(StrixRunnerExecTicketError, match="signature mismatch"):
        verify_strix_runner_exec_ticket(
            ticket.to_dict(),
            session_id="sess-1",
            request_id="req-1",
            argv=["curl", "-fsS", "http://127.0.0.1:48080/graphql"],
            timeout_seconds=10.0,
            verification_secret="wrong-runner-ticket-secret-at-least-32-bytes",
        )


@pytest.mark.parametrize(
    ("session_id", "request_id", "argv", "timeout_seconds"),
    (
        (
            "sess-2",
            "req-1",
            ["curl", "-fsS", "http://127.0.0.1:48080/graphql"],
            10.0,
        ),
        (
            "sess-1",
            "req-2",
            ["curl", "-fsS", "http://127.0.0.1:48080/graphql"],
            10.0,
        ),
        (
            "sess-1",
            "req-1",
            ["curl", "-I", "http://127.0.0.1:48080/"],
            10.0,
        ),
        (
            "sess-1",
            "req-1",
            ["curl", "-fsS", "http://127.0.0.1:48080/graphql"],
            11.0,
        ),
    ),
)
def test_exec_ticket_rejects_request_binding_mismatch(
    session_id,
    request_id,
    argv,
    timeout_seconds,
):
    ticket = build_strix_runner_exec_ticket(
        _descriptor(),
        signing_secret=SECRET,
    )

    with pytest.raises(StrixRunnerExecTicketError, match="does not match request"):
        verify_strix_runner_exec_ticket(
            ticket.to_dict(),
            session_id=session_id,
            request_id=request_id,
            argv=argv,
            timeout_seconds=timeout_seconds,
            verification_secret=SECRET,
        )


def test_exec_ticket_secret_requires_minimum_entropy_length():
    with pytest.raises(StrixRunnerExecTicketError, match="at least 32 bytes"):
        validate_strix_runner_exec_ticket_secret("too-short")
