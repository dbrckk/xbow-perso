from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


class ScannerSandboxConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ScannerSandboxAdmission:
    ready: bool
    profile: str
    worker_role: str
    read_only_rootfs: bool
    no_new_privileges: bool
    cap_drop_all: bool
    dedicated_worker: bool
    allowed_engines: tuple[str, ...]
    block_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_engines"] = list(self.allowed_engines)
        payload["block_reasons"] = list(self.block_reasons)
        return payload


def _strict_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ScannerSandboxConfigError(f"{name} must be a boolean")


def _allowed_engines() -> tuple[str, ...]:
    raw = os.getenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei").strip()
    if not raw:
        return ()
    engines = tuple(sorted({item.strip().lower() for item in raw.split(",") if item.strip()}))
    supported = {"nuclei", "strix"}
    if any(item not in supported for item in engines):
        raise ScannerSandboxConfigError(
            "XBOW_SCANNER_ALLOWED_ENGINES contains unsupported engine"
        )
    return engines


def scanner_sandbox_admission(engine: str | None = None) -> ScannerSandboxAdmission:
    worker_role = (os.getenv("XBOW_WORKER_ROLE") or "").strip().lower()
    profile = (os.getenv("XBOW_SCANNER_SANDBOX_PROFILE") or "").strip().lower()
    read_only_rootfs = _strict_bool("XBOW_SANDBOX_READ_ONLY_ROOTFS", False)
    no_new_privileges = _strict_bool("XBOW_SANDBOX_NO_NEW_PRIVILEGES", False)
    cap_drop_all = _strict_bool("XBOW_SANDBOX_CAP_DROP_ALL", False)
    allowed_engines = _allowed_engines()
    scanner_worker_enabled = _strict_bool("XBOW_ENABLE_SCANNER_WORKER", False)

    reasons: list[str] = []
    if not scanner_worker_enabled:
        reasons.append("scanner_worker_disabled")
    if worker_role != "scanner":
        reasons.append("dedicated_scanner_worker_required")
    if profile != "restricted-v1":
        reasons.append("restricted_sandbox_profile_required")
    if not read_only_rootfs:
        reasons.append("read_only_rootfs_not_attested")
    if not no_new_privileges:
        reasons.append("no_new_privileges_not_attested")
    if not cap_drop_all:
        reasons.append("cap_drop_all_not_attested")
    if engine is not None and engine.lower() not in allowed_engines:
        reasons.append("engine_not_allowlisted")

    return ScannerSandboxAdmission(
        ready=not reasons,
        profile=profile or "unconfigured",
        worker_role=worker_role or "unconfigured",
        read_only_rootfs=read_only_rootfs,
        no_new_privileges=no_new_privileges,
        cap_drop_all=cap_drop_all,
        dedicated_worker=worker_role == "scanner",
        allowed_engines=allowed_engines,
        block_reasons=tuple(reasons),
    )


def safe_scanner_sandbox_admission(engine: str | None = None) -> dict[str, Any]:
    try:
        return scanner_sandbox_admission(engine).to_dict()
    except ScannerSandboxConfigError:
        return {
            "ready": False,
            "profile": "configuration_error",
            "worker_role": "unconfigured",
            "read_only_rootfs": False,
            "no_new_privileges": False,
            "cap_drop_all": False,
            "dedicated_worker": False,
            "allowed_engines": [],
            "block_reasons": ["invalid_sandbox_configuration"],
            "configuration_error": True,
        }


def require_scanner_sandbox(engine: str) -> ScannerSandboxAdmission:
    admission = scanner_sandbox_admission(engine)
    if not admission.ready:
        raise ScannerSandboxConfigError(
            "scanner sandbox admission blocked: " + ",".join(admission.block_reasons)
        )
    return admission
