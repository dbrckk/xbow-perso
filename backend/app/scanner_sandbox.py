from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
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
    runtime_read_only_rootfs: bool
    runtime_no_new_privileges: bool
    runtime_cap_drop_all: bool
    runtime_attested: bool
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


def _runtime_hardening_attestation() -> dict[str, bool]:
    """Verify Linux sandbox properties from the running process, fail-closed."""
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8")
        status_fields = {}
        for line in status.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            status_fields[key.strip()] = value.strip()

        no_new_privileges = status_fields.get("NoNewPrivs") == "1"
        cap_eff_raw = status_fields.get("CapEff")
        cap_drop_all = bool(cap_eff_raw) and int(cap_eff_raw, 16) == 0

        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
        rootfs_read_only = False
        for line in mountinfo.splitlines():
            parts = line.split()
            if len(parts) < 6:
                continue
            if parts[4] != "/":
                continue
            mount_options = set(parts[5].split(","))
            rootfs_read_only = "ro" in mount_options and "rw" not in mount_options
            break

        return {
            "read_only_rootfs": rootfs_read_only,
            "no_new_privileges": no_new_privileges,
            "cap_drop_all": cap_drop_all,
        }
    except (OSError, ValueError):
        return {
            "read_only_rootfs": False,
            "no_new_privileges": False,
            "cap_drop_all": False,
        }


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
    runtime = _runtime_hardening_attestation()
    runtime_read_only_rootfs = bool(runtime.get("read_only_rootfs"))
    runtime_no_new_privileges = bool(runtime.get("no_new_privileges"))
    runtime_cap_drop_all = bool(runtime.get("cap_drop_all"))
    runtime_attested = (
        runtime_read_only_rootfs
        and runtime_no_new_privileges
        and runtime_cap_drop_all
    )

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
    if read_only_rootfs and not runtime_read_only_rootfs:
        reasons.append("runtime_rootfs_not_read_only")
    if no_new_privileges and not runtime_no_new_privileges:
        reasons.append("runtime_no_new_privileges_missing")
    if cap_drop_all and not runtime_cap_drop_all:
        reasons.append("runtime_capabilities_present")
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
        runtime_read_only_rootfs=runtime_read_only_rootfs,
        runtime_no_new_privileges=runtime_no_new_privileges,
        runtime_cap_drop_all=runtime_cap_drop_all,
        runtime_attested=runtime_attested,
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
            "runtime_read_only_rootfs": False,
            "runtime_no_new_privileges": False,
            "runtime_cap_drop_all": False,
            "runtime_attested": False,
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
