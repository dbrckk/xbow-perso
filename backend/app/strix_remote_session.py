from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Sequence
from uuid import uuid4


STRIX_REMOTE_SESSION_SCHEMA = "strix-remote-session-interface-v1"
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


class StrixRemoteSessionError(RuntimeError):
    pass


class StrixRemoteSessionBlocked(StrixRemoteSessionError):
    pass


@dataclass(frozen=True)
class PreparedRemoteSessionDescriptor:
    schema: str
    session_id: str
    image: str
    exposed_ports: tuple[int, ...]
    manifest_present: bool
    manifest_materialized: bool
    bind_mounts_supported: bool
    active_execution_enabled: bool
    network_io_performed: bool
    process_execution_performed: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["exposed_ports"] = list(self.exposed_ports)
        return payload


@dataclass(frozen=True)
class PreparedRemoteOperation:
    schema: str
    operation: str
    session_id: str
    request_id: str
    executable: str | None
    argv_sha256: str | None
    argc: int
    timeout_seconds: float | None
    port: int | None
    network_io_performed: bool
    process_execution_performed: bool
    active_execution_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _valid_session_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise StrixRemoteSessionError("prepared remote session id is invalid")
    return value


def _validate_image(image: str) -> str:
    if (
        not isinstance(image, str)
        or not 1 <= len(image) <= 512
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in image)
    ):
        raise StrixRemoteSessionError("prepared remote session image is invalid")
    return image


def _validate_ports(exposed_ports: Sequence[int]) -> tuple[int, ...]:
    if isinstance(exposed_ports, (str, bytes)) or len(exposed_ports) > 16:
        raise StrixRemoteSessionError("prepared remote exposed ports are invalid")
    ports: list[int] = []
    for port in exposed_ports:
        if (
            not isinstance(port, int)
            or isinstance(port, bool)
            or not 1 <= port <= 65535
        ):
            raise StrixRemoteSessionError("prepared remote exposed port is invalid")
        ports.append(port)
    if len(set(ports)) != len(ports):
        raise StrixRemoteSessionError("prepared remote exposed ports contain duplicates")
    return tuple(ports)


def _new_session_id() -> str:
    return f"prepared-{uuid4().hex}"


def _new_request_id(operation: str) -> str:
    return f"{operation}-{uuid4().hex}"


def _validate_exec(
    argv: Sequence[str],
    timeout_seconds: float | int | None,
) -> tuple[str, str, int, float]:
    if isinstance(argv, (str, bytes)) or not 1 <= len(argv) <= 64:
        raise StrixRemoteSessionError("prepared remote argv is invalid")

    normalized: list[str] = []
    total_bytes = 0
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
            raise StrixRemoteSessionError("prepared remote argv is invalid")
        total_bytes += len(arg.encode("utf-8"))
        normalized.append(arg)
    if total_bytes > 16 * 1024:
        raise StrixRemoteSessionError("prepared remote argv exceeds byte limit")

    executable = normalized[0]
    if (
        not _EXECUTABLE_RE.fullmatch(executable)
        or "/" in executable
        or "\\" in executable
        or executable in _SHELL_INTERPRETERS
    ):
        raise StrixRemoteSessionError(
            "prepared remote executable is not admissible"
        )

    timeout = 30.0 if timeout_seconds is None else float(timeout_seconds)
    if not math.isfinite(timeout) or not 0.1 <= timeout <= 600.0:
        raise StrixRemoteSessionError("prepared remote timeout is invalid")

    canonical = "\x00".join(normalized).encode("utf-8")
    return (
        executable,
        hashlib.sha256(canonical).hexdigest(),
        len(normalized),
        timeout,
    )


class PreparedStrixRemoteSession:
    def __init__(self, descriptor: PreparedRemoteSessionDescriptor) -> None:
        if descriptor.schema != STRIX_REMOTE_SESSION_SCHEMA:
            raise StrixRemoteSessionError(
                "prepared remote session descriptor schema is unsupported"
            )
        _valid_session_id(descriptor.session_id)
        if (
            descriptor.manifest_materialized
            or descriptor.bind_mounts_supported
            or descriptor.active_execution_enabled
            or descriptor.network_io_performed
            or descriptor.process_execution_performed
        ):
            raise StrixRemoteSessionError(
                "prepared remote session safety invariants changed"
            )
        self.descriptor = descriptor

    @property
    def session_id(self) -> str:
        return self.descriptor.session_id

    def plan_exec(
        self,
        *args: str,
        timeout: float | int | None = None,
    ) -> PreparedRemoteOperation:
        executable, argv_sha256, argc, normalized_timeout = _validate_exec(
            args,
            timeout,
        )
        return PreparedRemoteOperation(
            schema=STRIX_REMOTE_SESSION_SCHEMA,
            operation="exec",
            session_id=self.session_id,
            request_id=_new_request_id("exec"),
            executable=executable,
            argv_sha256=argv_sha256,
            argc=argc,
            timeout_seconds=normalized_timeout,
            port=None,
            network_io_performed=False,
            process_execution_performed=False,
            active_execution_enabled=False,
        )

    async def exec(
        self,
        *args: str,
        timeout: float | int | None = None,
        **_kwargs: Any,
    ) -> Any:
        self.plan_exec(*args, timeout=timeout)
        raise StrixRemoteSessionBlocked(
            "prepared Strix remote session exec is not enabled"
        )

    def plan_resolve_exposed_port(self, port: int) -> PreparedRemoteOperation:
        if (
            not isinstance(port, int)
            or isinstance(port, bool)
            or port not in self.descriptor.exposed_ports
        ):
            raise StrixRemoteSessionError(
                "prepared remote exposed port was not declared"
            )
        return PreparedRemoteOperation(
            schema=STRIX_REMOTE_SESSION_SCHEMA,
            operation="resolve-port",
            session_id=self.session_id,
            request_id=_new_request_id("port"),
            executable=None,
            argv_sha256=None,
            argc=0,
            timeout_seconds=None,
            port=port,
            network_io_performed=False,
            process_execution_performed=False,
            active_execution_enabled=False,
        )

    async def resolve_exposed_port(self, port: int) -> Any:
        self.plan_resolve_exposed_port(port)
        raise StrixRemoteSessionBlocked(
            "prepared Strix remote port resolution is not enabled"
        )


class PreparedStrixRemoteClient:
    def __init__(self, session: PreparedStrixRemoteSession) -> None:
        self._session = session

    def plan_delete(self, session: PreparedStrixRemoteSession) -> PreparedRemoteOperation:
        if session is not self._session:
            raise StrixRemoteSessionError(
                "prepared remote client session mismatch"
            )
        return PreparedRemoteOperation(
            schema=STRIX_REMOTE_SESSION_SCHEMA,
            operation="delete",
            session_id=session.session_id,
            request_id=_new_request_id("delete"),
            executable=None,
            argv_sha256=None,
            argc=0,
            timeout_seconds=None,
            port=None,
            network_io_performed=False,
            process_execution_performed=False,
            active_execution_enabled=False,
        )

    async def delete(self, session: PreparedStrixRemoteSession) -> Any:
        self.plan_delete(session)
        raise StrixRemoteSessionBlocked(
            "prepared Strix remote session deletion is not enabled"
        )


async def prepare_strix_remote_session(
    *,
    image: str,
    manifest: Any,
    exposed_ports: Sequence[int],
    bind_mounts: list[dict[str, Any]] | None = None,
) -> tuple[PreparedStrixRemoteClient, PreparedStrixRemoteSession]:
    if bind_mounts:
        raise StrixRemoteSessionError(
            "prepared Strix remote sessions do not support bind mounts"
        )
    if manifest is not None:
        from .strix_manifest_admission import (
            StrixManifestAdmissionError,
            build_strix_manifest_admission_plan,
        )

        try:
            manifest_plan = build_strix_manifest_admission_plan(manifest)
        except StrixManifestAdmissionError as exc:
            raise StrixRemoteSessionError(
                f"prepared Strix manifest rejected: {exc}"
            ) from exc
        if (
            manifest_plan.manifest_materialized
            or manifest_plan.upload_enabled
            or manifest_plan.filesystem_io_performed
            or manifest_plan.host_paths_included
            or manifest_plan.raw_file_content_included
        ):
            raise StrixRemoteSessionError(
                "prepared Strix manifest safety invariants changed"
            )
    descriptor = PreparedRemoteSessionDescriptor(
        schema=STRIX_REMOTE_SESSION_SCHEMA,
        session_id=_new_session_id(),
        image=_validate_image(image),
        exposed_ports=_validate_ports(exposed_ports),
        manifest_present=manifest is not None,
        manifest_materialized=False,
        bind_mounts_supported=False,
        active_execution_enabled=False,
        network_io_performed=False,
        process_execution_performed=False,
    )
    session = PreparedStrixRemoteSession(descriptor)
    return PreparedStrixRemoteClient(session), session


def prepared_remote_session_self_test() -> dict[str, Any]:
    descriptor = PreparedRemoteSessionDescriptor(
        schema=STRIX_REMOTE_SESSION_SCHEMA,
        session_id="prepared-self-test",
        image="fixture",
        exposed_ports=(48080,),
        manifest_present=True,
        manifest_materialized=False,
        bind_mounts_supported=False,
        active_execution_enabled=False,
        network_io_performed=False,
        process_execution_performed=False,
    )
    session = PreparedStrixRemoteSession(descriptor)
    exec_plan = session.plan_exec(
        "curl",
        "-fsS",
        "http://127.0.0.1:48080/graphql",
        timeout=15,
    )
    port_plan = session.plan_resolve_exposed_port(48080)
    canonical = json.dumps(
        {
            "descriptor": descriptor.to_dict(),
            "exec": exec_plan.to_dict(),
            "port": port_plan.to_dict(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema": STRIX_REMOTE_SESSION_SCHEMA,
        "self_test_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "client_interface_defined": True,
        "session_interface_defined": True,
        "exec_signature_compatible": True,
        "resolve_exposed_port_async": True,
        "delete_async": True,
        "manifest_materialized": False,
        "network_io_performed": False,
        "process_execution_performed": False,
        "active_execution_enabled": False,
    }
