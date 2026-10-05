from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Sequence

from .strix_execution_contract import (
    STRIX_EXECUTION_CONTRACT_SCHEMA,
    StrixExecutionContract,
    StrixExecutionContractError,
    verify_strix_contract_integrity,
)


STRIX_COMMAND_ADMISSION_SCHEMA = "strix-command-admission-v1"
STRIX_BOOTSTRAP_PROFILE = "bootstrap-v1"
STRIX_WEB_ACTIVE_PROFILE = "web-active-v1"

STRIX_BOOTSTRAP_EXECUTABLES = frozenset({"curl"})
STRIX_WEB_ACTIVE_EXECUTABLES = frozenset(
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
)

_PROFILE_EXECUTABLES = {
    STRIX_BOOTSTRAP_PROFILE: STRIX_BOOTSTRAP_EXECUTABLES,
    STRIX_WEB_ACTIVE_PROFILE: STRIX_WEB_ACTIVE_EXECUTABLES,
}
_PROFILE_MAX_TIMEOUT_SECONDS = {
    STRIX_BOOTSTRAP_PROFILE: 30.0,
    STRIX_WEB_ACTIVE_PROFILE: 300.0,
}

_MAX_ARGC = 64
_MAX_ARG_BYTES = 4096
_MAX_TOTAL_ARG_BYTES = 16 * 1024
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_EXECUTABLE_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
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


class StrixCommandAdmissionError(RuntimeError):
    pass


@dataclass(frozen=True)
class StrixAuthorizedCommand:
    schema: str
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "contract_hash": self.contract_hash,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "profile": self.profile,
            "executable": self.executable,
            "argv_sha256": self.argv_sha256,
            "argc": self.argc,
            "argv_bytes": self.argv_bytes,
            "timeout_seconds": self.timeout_seconds,
            "shell_interpreter_allowed": self.shell_interpreter_allowed,
            "direct_egress_allowed": self.direct_egress_allowed,
            "network_scope_enforcement": self.network_scope_enforcement,
            "active_execution_enabled": self.active_execution_enabled,
        }


def reviewed_command_profiles() -> dict[str, dict[str, Any]]:
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


def _valid_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise StrixCommandAdmissionError(
            f"Strix command {name} is invalid"
        )
    return value


def _validate_contract(
    contract: StrixExecutionContract,
    *,
    verification_secret: str | None,
) -> None:
    try:
        verify_strix_contract_integrity(
            contract,
            require_signature=True,
            verification_secret=verification_secret,
        )
    except StrixExecutionContractError as exc:
        raise StrixCommandAdmissionError(
            "Strix command execution contract is not authenticated"
        ) from exc

    if (
        contract.schema != STRIX_EXECUTION_CONTRACT_SCHEMA
        or contract.engine != "strix"
    ):
        raise StrixCommandAdmissionError(
            "Strix command execution contract is unsupported"
        )
    if (
        contract.direct_egress_allowed
        or contract.host_container_socket_allowed
        or not contract.independent_validation_required
    ):
        raise StrixCommandAdmissionError(
            "Strix command execution contract safety invariants changed"
        )


def _validate_argv(
    argv: Sequence[str],
    *,
    profile: str,
) -> tuple[str, int]:
    if profile not in _PROFILE_EXECUTABLES:
        raise StrixCommandAdmissionError(
            "Strix command profile is unsupported"
        )
    if isinstance(argv, (str, bytes)) or not 1 <= len(argv) <= _MAX_ARGC:
        raise StrixCommandAdmissionError("Strix command argv is invalid")

    encoded_total = 0
    normalized: list[str] = []
    for arg in argv:
        if (
            not isinstance(arg, str)
            or not 1 <= len(arg) <= _MAX_ARG_BYTES
            or any(
                ord(char) < 0x20 and char != "\t"
                or ord(char) == 0x7F
                for char in arg
            )
        ):
            raise StrixCommandAdmissionError(
                "Strix command argv is invalid"
            )
        encoded_total += len(arg.encode("utf-8"))
        normalized.append(arg)
    if encoded_total > _MAX_TOTAL_ARG_BYTES:
        raise StrixCommandAdmissionError(
            "Strix command argv exceeds byte limit"
        )

    executable = normalized[0]
    if (
        not _EXECUTABLE_RE.fullmatch(executable)
        or "/" in executable
        or "\\" in executable
    ):
        raise StrixCommandAdmissionError(
            "Strix command executable path is not admitted"
        )
    if executable in _SHELL_INTERPRETERS:
        raise StrixCommandAdmissionError(
            "Strix command shell interpreter is not admitted"
        )
    if executable not in _PROFILE_EXECUTABLES[profile]:
        raise StrixCommandAdmissionError(
            "Strix command executable is outside reviewed profile"
        )
    return executable, encoded_total


def authorize_strix_command(
    contract: StrixExecutionContract,
    *,
    session_id: str,
    request_id: str,
    profile: str,
    argv: Sequence[str],
    timeout_seconds: float,
    verification_secret: str | None = None,
) -> StrixAuthorizedCommand:
    """Authorize one future sandbox command without executing it.

    Network scope is deliberately *not* inferred from argv. The execution
    contract requires direct egress to remain disabled, so target traffic must
    still cross the separately scoped broker boundary.
    """

    _validate_contract(
        contract,
        verification_secret=verification_secret,
    )
    session_id = _valid_id(session_id, "session id")
    request_id = _valid_id(request_id, "request id")
    executable, argv_bytes = _validate_argv(argv, profile=profile)

    try:
        timeout = float(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise StrixCommandAdmissionError(
            "Strix command timeout is invalid"
        ) from exc
    max_timeout = _PROFILE_MAX_TIMEOUT_SECONDS.get(profile)
    if (
        max_timeout is None
        or timeout != timeout
        or timeout in {float("inf"), float("-inf")}
        or timeout < 0.1
        or timeout > max_timeout
    ):
        raise StrixCommandAdmissionError(
            "Strix command timeout exceeds reviewed profile"
        )

    canonical_argv = "\x00".join(argv).encode("utf-8")
    return StrixAuthorizedCommand(
        schema=STRIX_COMMAND_ADMISSION_SCHEMA,
        contract_hash=contract.contract_hash,
        session_id=session_id,
        request_id=request_id,
        profile=profile,
        executable=executable,
        argv_sha256=hashlib.sha256(canonical_argv).hexdigest(),
        argc=len(argv),
        argv_bytes=argv_bytes,
        timeout_seconds=timeout,
        shell_interpreter_allowed=False,
        direct_egress_allowed=False,
        network_scope_enforcement="broker_required",
        active_execution_enabled=False,
    )
