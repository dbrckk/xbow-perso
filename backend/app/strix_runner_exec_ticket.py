from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


STRIX_RUNNER_EXEC_TICKET_SCHEMA = "strix-runner-exec-ticket-v1"
STRIX_COMMAND_ADMISSION_SCHEMA = "strix-command-admission-v1"
STRIX_RUNNER_EXEC_TICKET_MIN_SECRET_BYTES = 32
STRIX_RUNNER_EXEC_TICKET_MAX_SECRET_BYTES = 4096

_SIGNATURE_DOMAIN = b"xbow:strix-runner-exec-ticket:v1\x00"
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_PROFILE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_EXECUTABLE_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHELL_INTERPRETERS = frozenset(
    {
        "ash",
        "bash",
        "busybox",
        "dash",
        "env",
        "fish",
        "node",
        "perl",
        "php",
        "python",
        "python3",
        "ruby",
        "sh",
        "zsh",
    }
)

_PROFILE_EXECUTABLES = {
    "bootstrap-v1": frozenset({"curl"}),
    "web-active-v1": frozenset(
        {
            "curl",
            "dalfox",
            "feroxbuster",
            "ffuf",
            "gobuster",
            "httpx",
            "katana",
            "nikto",
            "nuclei",
            "sqlmap",
        }
    ),
}
_PROFILE_MAX_TIMEOUT_SECONDS = {
    "bootstrap-v1": 30.0,
    "web-active-v1": 300.0,
}


class StrixRunnerExecTicketError(RuntimeError):
    pass


@dataclass(frozen=True)
class StrixRunnerExecTicket:
    schema: str
    command_schema: str
    contract_hash: str
    session_id: str
    request_id: str
    profile: str
    executable: str
    argv_sha256: str
    argc: int
    argv_bytes: int
    timeout_seconds: float
    shell_interpreter_allowed: bool
    direct_egress_allowed: bool
    network_scope_enforcement: str
    active_execution_enabled: bool
    signature_alg: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _secret_bytes(secret: str) -> bytes:
    if not isinstance(secret, str):
        raise StrixRunnerExecTicketError("runner exec ticket secret must be text")
    encoded = secret.encode("utf-8")
    if len(encoded) < STRIX_RUNNER_EXEC_TICKET_MIN_SECRET_BYTES:
        raise StrixRunnerExecTicketError(
            "runner exec ticket secret must be at least 32 bytes"
        )
    if len(encoded) > STRIX_RUNNER_EXEC_TICKET_MAX_SECRET_BYTES:
        raise StrixRunnerExecTicketError(
            "runner exec ticket secret exceeds maximum size"
        )
    return encoded


def validate_strix_runner_exec_ticket_secret(secret: str) -> None:
    _secret_bytes(secret)


def _argv_digest(argv: Sequence[str]) -> tuple[str, int, int, str]:
    if isinstance(argv, (str, bytes)) or not 1 <= len(argv) <= 64:
        raise StrixRunnerExecTicketError("runner exec argv is invalid")

    normalized: list[str] = []
    argv_bytes = 0
    for arg in argv:
        if (
            not isinstance(arg, str)
            or not 1 <= len(arg) <= 4096
            or any(
                (ord(char) < 0x20 and char != "\t")
                or ord(char) == 0x7F
                for char in arg
            )
        ):
            raise StrixRunnerExecTicketError("runner exec argv is invalid")
        normalized.append(arg)
        argv_bytes += len(arg.encode("utf-8"))
    if argv_bytes > 16 * 1024:
        raise StrixRunnerExecTicketError("runner exec argv exceeds byte limit")

    executable = normalized[0]
    if (
        not _EXECUTABLE_RE.fullmatch(executable)
        or "/" in executable
        or "\\" in executable
        or executable in _SHELL_INTERPRETERS
    ):
        raise StrixRunnerExecTicketError(
            "runner exec executable is not admitted"
        )

    canonical = "\x00".join(normalized).encode("utf-8")
    return (
        hashlib.sha256(canonical).hexdigest(),
        len(normalized),
        argv_bytes,
        executable,
    )


def _unsigned_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": STRIX_RUNNER_EXEC_TICKET_SCHEMA,
        "command_schema": STRIX_COMMAND_ADMISSION_SCHEMA,
        "contract_hash": values["contract_hash"],
        "session_id": values["session_id"],
        "request_id": values["request_id"],
        "profile": values["profile"],
        "executable": values["executable"],
        "argv_sha256": values["argv_sha256"],
        "argc": values["argc"],
        "argv_bytes": values["argv_bytes"],
        "timeout_seconds": values["timeout_seconds"],
        "shell_interpreter_allowed": values["shell_interpreter_allowed"],
        "direct_egress_allowed": values["direct_egress_allowed"],
        "network_scope_enforcement": values["network_scope_enforcement"],
        "active_execution_enabled": values["active_execution_enabled"],
    }


def _canonical_bytes(values: Mapping[str, Any]) -> bytes:
    return json.dumps(
        _unsigned_payload(values),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _validate_descriptor(values: Mapping[str, Any]) -> None:
    if values.get("schema") != STRIX_COMMAND_ADMISSION_SCHEMA:
        raise StrixRunnerExecTicketError(
            "runner exec command descriptor schema is unsupported"
        )
    if not isinstance(values.get("contract_hash"), str) or not _SHA256_RE.fullmatch(
        values["contract_hash"]
    ):
        raise StrixRunnerExecTicketError(
            "runner exec contract hash is invalid"
        )
    for name in ("session_id", "request_id"):
        value = values.get(name)
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            raise StrixRunnerExecTicketError(
                f"runner exec {name} is invalid"
            )
    profile = values.get("profile")
    executable = values.get("executable")
    if (
        not isinstance(profile, str)
        or not _PROFILE_RE.fullmatch(profile)
        or profile not in _PROFILE_EXECUTABLES
    ):
        raise StrixRunnerExecTicketError("runner exec profile is invalid")
    if (
        not isinstance(executable, str)
        or not _EXECUTABLE_RE.fullmatch(executable)
        or "/" in executable
        or "\\" in executable
        or executable in _SHELL_INTERPRETERS
        or executable not in _PROFILE_EXECUTABLES[profile]
    ):
        raise StrixRunnerExecTicketError(
            "runner exec executable is not admitted"
        )
    if not isinstance(values.get("argv_sha256"), str) or not _SHA256_RE.fullmatch(
        values["argv_sha256"]
    ):
        raise StrixRunnerExecTicketError("runner exec argv digest is invalid")
    argc = values.get("argc")
    argv_bytes = values.get("argv_bytes")
    if not isinstance(argc, int) or isinstance(argc, bool) or not 1 <= argc <= 64:
        raise StrixRunnerExecTicketError("runner exec argc is invalid")
    if (
        not isinstance(argv_bytes, int)
        or isinstance(argv_bytes, bool)
        or not 1 <= argv_bytes <= 16 * 1024
    ):
        raise StrixRunnerExecTicketError("runner exec argv byte count is invalid")
    try:
        timeout = float(values.get("timeout_seconds"))
    except (TypeError, ValueError) as exc:
        raise StrixRunnerExecTicketError("runner exec timeout is invalid") from exc
    if (
        not math.isfinite(timeout)
        or timeout < 0.1
        or timeout > _PROFILE_MAX_TIMEOUT_SECONDS[profile]
    ):
        raise StrixRunnerExecTicketError("runner exec timeout is invalid")
    if (
        values.get("shell_interpreter_allowed") is not False
        or values.get("direct_egress_allowed") is not False
        or values.get("network_scope_enforcement") != "broker_required"
        or values.get("active_execution_enabled") is not False
    ):
        raise StrixRunnerExecTicketError(
            "runner exec safety invariants changed"
        )


def reviewed_runner_exec_ticket_profiles() -> dict[str, dict[str, Any]]:
    return {
        profile: {
            "executables": sorted(executables),
            "max_timeout_seconds": _PROFILE_MAX_TIMEOUT_SECONDS[profile],
            "shell_interpreters_allowed": False,
            "direct_egress_allowed": False,
            "network_scope_enforcement": "broker_required",
        }
        for profile, executables in _PROFILE_EXECUTABLES.items()
    }


def build_strix_runner_exec_ticket(
    command_descriptor: Mapping[str, Any],
    *,
    signing_secret: str,
) -> StrixRunnerExecTicket:
    _validate_descriptor(command_descriptor)
    secret = _secret_bytes(signing_secret)
    unsigned = _unsigned_payload(command_descriptor)
    signature = hmac.new(
        secret,
        _SIGNATURE_DOMAIN + _canonical_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    return StrixRunnerExecTicket(
        **unsigned,
        signature_alg="hmac-sha256",
        signature=signature,
    )


def verify_strix_runner_exec_ticket(
    ticket_payload: Mapping[str, Any],
    *,
    session_id: str,
    request_id: str,
    argv: Sequence[str],
    timeout_seconds: float,
    verification_secret: str,
) -> StrixRunnerExecTicket:
    expected_keys = {
        "schema",
        "command_schema",
        "contract_hash",
        "session_id",
        "request_id",
        "profile",
        "executable",
        "argv_sha256",
        "argc",
        "argv_bytes",
        "timeout_seconds",
        "shell_interpreter_allowed",
        "direct_egress_allowed",
        "network_scope_enforcement",
        "active_execution_enabled",
        "signature_alg",
        "signature",
    }
    if set(ticket_payload) != expected_keys:
        raise StrixRunnerExecTicketError("runner exec ticket shape is invalid")

    descriptor = {
        "schema": ticket_payload.get("command_schema"),
        "contract_hash": ticket_payload.get("contract_hash"),
        "session_id": ticket_payload.get("session_id"),
        "request_id": ticket_payload.get("request_id"),
        "profile": ticket_payload.get("profile"),
        "executable": ticket_payload.get("executable"),
        "argv_sha256": ticket_payload.get("argv_sha256"),
        "argc": ticket_payload.get("argc"),
        "argv_bytes": ticket_payload.get("argv_bytes"),
        "timeout_seconds": ticket_payload.get("timeout_seconds"),
        "shell_interpreter_allowed": ticket_payload.get("shell_interpreter_allowed"),
        "direct_egress_allowed": ticket_payload.get("direct_egress_allowed"),
        "network_scope_enforcement": ticket_payload.get("network_scope_enforcement"),
        "active_execution_enabled": ticket_payload.get("active_execution_enabled"),
    }
    _validate_descriptor(descriptor)
    if ticket_payload.get("schema") != STRIX_RUNNER_EXEC_TICKET_SCHEMA:
        raise StrixRunnerExecTicketError(
            "runner exec ticket schema is unsupported"
        )
    if ticket_payload.get("signature_alg") != "hmac-sha256":
        raise StrixRunnerExecTicketError(
            "runner exec ticket signature algorithm is unsupported"
        )
    signature = ticket_payload.get("signature")
    if not isinstance(signature, str) or not _SHA256_RE.fullmatch(signature):
        raise StrixRunnerExecTicketError(
            "runner exec ticket signature is invalid"
        )

    secret = _secret_bytes(verification_secret)
    expected_signature = hmac.new(
        secret,
        _SIGNATURE_DOMAIN + _canonical_bytes(ticket_payload),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise StrixRunnerExecTicketError(
            "runner exec ticket signature mismatch"
        )

    digest, argc, argv_bytes, executable = _argv_digest(argv)
    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise StrixRunnerExecTicketError("runner exec timeout is invalid") from exc
    if not math.isfinite(timeout):
        raise StrixRunnerExecTicketError("runner exec timeout is invalid")

    if (
        ticket_payload["session_id"] != session_id
        or ticket_payload["request_id"] != request_id
        or ticket_payload["argv_sha256"] != digest
        or ticket_payload["argc"] != argc
        or ticket_payload["argv_bytes"] != argv_bytes
        or ticket_payload["executable"] != executable
        or float(ticket_payload["timeout_seconds"]) != timeout
    ):
        raise StrixRunnerExecTicketError(
            "runner exec ticket does not match request"
        )

    return StrixRunnerExecTicket(
        **{
            key: ticket_payload[key]
            for key in expected_keys
        }
    )
