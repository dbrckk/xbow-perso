from __future__ import annotations

import pytest

from app.strix_command_admission import (
    STRIX_BOOTSTRAP_PROFILE,
    STRIX_COMMAND_ADMISSION_SCHEMA,
    STRIX_WEB_ACTIVE_PROFILE,
    StrixCommandAdmissionError,
    authorize_strix_command,
    reviewed_command_profiles,
)
from app.strix_execution_contract import StrixExecutionContract


def _contract(**overrides) -> StrixExecutionContract:
    values = {
        "schema": "strix-execution-contract-v1",
        "engine": "strix",
        "campaign_id": "campaign-1",
        "job_id": "job-1",
        "primary_target": "https://example.com",
        "policy_fingerprint": "a" * 64,
        "allowed_targets": ("example.com",),
        "denied_targets": (),
        "max_requests_per_second": 2.0,
        "direct_egress_allowed": False,
        "host_container_socket_allowed": False,
        "independent_validation_required": True,
        "contract_hash": "b" * 64,
        "signature_alg": "hmac-sha256",
        "signature": "c" * 64,
    }
    values.update(overrides)
    return StrixExecutionContract(**values)


def _trust_contract(monkeypatch):
    calls = []

    def verify(contract, *, require_signature, verification_secret=None):
        calls.append(
            (
                contract.contract_hash,
                require_signature,
                verification_secret,
            )
        )

    monkeypatch.setattr(
        "app.strix_command_admission.verify_strix_contract_integrity",
        verify,
    )
    return calls


def test_reviewed_profiles_keep_shell_and_direct_egress_disabled():
    profiles = reviewed_command_profiles()

    assert profiles[STRIX_BOOTSTRAP_PROFILE] == {
        "executables": ["curl"],
        "max_timeout_seconds": 30.0,
        "shell_interpreters_allowed": False,
        "direct_egress_allowed": False,
        "network_scope_enforcement": "broker_required",
    }
    assert "nuclei" in profiles[STRIX_WEB_ACTIVE_PROFILE]["executables"]
    assert "sqlmap" in profiles[STRIX_WEB_ACTIVE_PROFILE]["executables"]
    assert "ffuf" in profiles[STRIX_WEB_ACTIVE_PROFILE]["executables"]
    assert profiles[STRIX_WEB_ACTIVE_PROFILE]["shell_interpreters_allowed"] is False
    assert profiles[STRIX_WEB_ACTIVE_PROFILE]["direct_egress_allowed"] is False


def test_bootstrap_curl_is_admitted_without_enabling_execution(monkeypatch):
    calls = _trust_contract(monkeypatch)

    result = authorize_strix_command(
        _contract(),
        session_id="session-1",
        request_id="request-1",
        profile=STRIX_BOOTSTRAP_PROFILE,
        argv=[
            "curl",
            "-fsS",
            "http://127.0.0.1:48080/graphql",
        ],
        timeout_seconds=15,
        verification_secret="verification-key",
    )

    assert calls == [
        (
            "b" * 64,
            True,
            "verification-key",
        )
    ]
    assert result.schema == STRIX_COMMAND_ADMISSION_SCHEMA
    assert result.contract_hash == "b" * 64
    assert result.profile == STRIX_BOOTSTRAP_PROFILE
    assert result.executable == "curl"
    assert result.argc == 3
    assert result.timeout_seconds == 15.0
    assert result.shell_interpreter_allowed is False
    assert result.direct_egress_allowed is False
    assert result.network_scope_enforcement == "broker_required"
    assert result.active_execution_enabled is False
    assert len(result.argv_sha256) == 64


@pytest.mark.parametrize(
    "executable",
    (
        "nuclei",
        "sqlmap",
        "ffuf",
        "katana",
        "dalfox",
        "feroxbuster",
        "gobuster",
        "httpx",
        "nikto",
    ),
)
def test_reviewed_web_active_tools_are_admissible(monkeypatch, executable):
    _trust_contract(monkeypatch)

    result = authorize_strix_command(
        _contract(),
        session_id="session-1",
        request_id="request-1",
        profile=STRIX_WEB_ACTIVE_PROFILE,
        argv=[executable, "--version"],
        timeout_seconds=30,
    )

    assert result.executable == executable
    assert result.profile == STRIX_WEB_ACTIVE_PROFILE
    assert result.active_execution_enabled is False


@pytest.mark.parametrize(
    "argv",
    (
        ["bash", "-lc", "id"],
        ["sh", "-c", "id"],
        ["python3", "-c", "print(1)"],
        ["/usr/bin/curl", "https://example.com"],
        ["../curl", "https://example.com"],
        ["curl", "bad\narg"],
    ),
)
def test_shells_paths_and_control_characters_fail_closed(monkeypatch, argv):
    _trust_contract(monkeypatch)

    with pytest.raises(StrixCommandAdmissionError):
        authorize_strix_command(
            _contract(),
            session_id="session-1",
            request_id="request-1",
            profile=STRIX_WEB_ACTIVE_PROFILE,
            argv=argv,
            timeout_seconds=30,
        )


def test_tool_outside_profile_is_rejected(monkeypatch):
    _trust_contract(monkeypatch)

    with pytest.raises(
        StrixCommandAdmissionError,
        match="outside reviewed profile",
    ):
        authorize_strix_command(
            _contract(),
            session_id="session-1",
            request_id="request-1",
            profile=STRIX_BOOTSTRAP_PROFILE,
            argv=["nuclei", "--version"],
            timeout_seconds=15,
        )


def test_profile_timeout_caps_are_enforced(monkeypatch):
    _trust_contract(monkeypatch)

    with pytest.raises(
        StrixCommandAdmissionError,
        match="timeout exceeds",
    ):
        authorize_strix_command(
            _contract(),
            session_id="session-1",
            request_id="request-1",
            profile=STRIX_BOOTSTRAP_PROFILE,
            argv=["curl", "--version"],
            timeout_seconds=31,
        )

    with pytest.raises(
        StrixCommandAdmissionError,
        match="timeout exceeds",
    ):
        authorize_strix_command(
            _contract(),
            session_id="session-1",
            request_id="request-1",
            profile=STRIX_WEB_ACTIVE_PROFILE,
            argv=["nuclei", "--version"],
            timeout_seconds=301,
        )


@pytest.mark.parametrize(
    "overrides",
    (
        {"direct_egress_allowed": True},
        {"host_container_socket_allowed": True},
        {"independent_validation_required": False},
        {"engine": "other"},
    ),
)
def test_contract_safety_drift_is_rejected(monkeypatch, overrides):
    _trust_contract(monkeypatch)

    with pytest.raises(StrixCommandAdmissionError):
        authorize_strix_command(
            _contract(**overrides),
            session_id="session-1",
            request_id="request-1",
            profile=STRIX_WEB_ACTIVE_PROFILE,
            argv=["nuclei", "--version"],
            timeout_seconds=30,
        )


def test_signature_verification_failure_is_wrapped(monkeypatch):
    def fail(*_args, **_kwargs):
        from app.strix_execution_contract import StrixExecutionContractError

        raise StrixExecutionContractError("bad signature")

    monkeypatch.setattr(
        "app.strix_command_admission.verify_strix_contract_integrity",
        fail,
    )

    with pytest.raises(
        StrixCommandAdmissionError,
        match="not authenticated",
    ):
        authorize_strix_command(
            _contract(),
            session_id="session-1",
            request_id="request-1",
            profile=STRIX_BOOTSTRAP_PROFILE,
            argv=["curl", "--version"],
            timeout_seconds=15,
        )


@pytest.mark.parametrize(
    ("session_id", "request_id"),
    (
        ("", "request-1"),
        ("session 1", "request-1"),
        ("session-1", ""),
        ("session-1", "request 1"),
    ),
)
def test_session_and_request_ids_are_bounded(
    monkeypatch,
    session_id,
    request_id,
):
    _trust_contract(monkeypatch)

    with pytest.raises(StrixCommandAdmissionError):
        authorize_strix_command(
            _contract(),
            session_id=session_id,
            request_id=request_id,
            profile=STRIX_BOOTSTRAP_PROFILE,
            argv=["curl", "--version"],
            timeout_seconds=15,
        )
