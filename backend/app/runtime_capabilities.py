from __future__ import annotations

import os
from typing import Any


class CapabilityConfigError(ValueError):
    pass


def _strict_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise CapabilityConfigError(f"{name} must be a boolean")


def pentagi_runtime_capability() -> dict[str, Any]:
    """Return a redacted, fail-closed summary of PentAGI runtime capability.

    Worker/transport switches are necessary runtime gates, but the current adapter
    still marks plans as non-executable because downstream scope/rate enforcement
    for remote PentAGI activity is not yet provable locally.
    """

    integration_enabled = _strict_bool("XBOW_ENABLE_PENTAGI", False)
    active_scans_enabled = _strict_bool("XBOW_ENABLE_ACTIVE_SCANS", False)
    dry_run = _strict_bool("DRY_RUN", True)
    worker_enabled = _strict_bool("XBOW_ENABLE_PENTAGI_WORKER", False)
    transport_enabled = _strict_bool("XBOW_ENABLE_PENTAGI_TRANSPORT", False)
    status_worker_enabled = _strict_bool(
        "XBOW_ENABLE_PENTAGI_STATUS_WORKER",
        False,
    )

    execution_transport_enforceable = False
    execution_reasons: list[str] = []
    if not integration_enabled:
        execution_reasons.append("pentagi_disabled")
    if not active_scans_enabled:
        execution_reasons.append("active_scans_disabled")
    if dry_run:
        execution_reasons.append("global_dry_run")
    if not worker_enabled:
        execution_reasons.append("pentagi_worker_disabled")
    if not transport_enabled:
        execution_reasons.append("pentagi_transport_disabled")
    if not execution_transport_enforceable:
        execution_reasons.append("execution_transport_not_enforceable")

    mode = "disabled" if not integration_enabled else "preview_only"

    return {
        "mode": mode,
        "integration_enabled": integration_enabled,
        "active_scans_enabled": active_scans_enabled,
        "dry_run": dry_run,
        "worker_enabled": worker_enabled,
        "transport_enabled": transport_enabled,
        "execution_transport_enforceable": execution_transport_enforceable,
        "dispatch_ready": not execution_reasons,
        "dispatch_block_reasons": execution_reasons,
        "status_tracking": {
            "worker_enabled": status_worker_enabled,
            "available": bool(integration_enabled and status_worker_enabled),
        },
        "contains_secrets": False,
    }


def safe_pentagi_runtime_capability() -> dict[str, Any]:
    """Return a fail-closed public capability document on configuration errors."""

    try:
        return pentagi_runtime_capability()
    except CapabilityConfigError:
        return {
            "mode": "configuration_error",
            "integration_enabled": False,
            "active_scans_enabled": False,
            "dry_run": True,
            "worker_enabled": False,
            "transport_enabled": False,
            "execution_transport_enforceable": False,
            "dispatch_ready": False,
            "dispatch_block_reasons": ["invalid_boolean_configuration"],
            "status_tracking": {
                "worker_enabled": False,
                "available": False,
            },
            "contains_secrets": False,
            "configuration_error": True,
        }


def scanner_runtime_capability() -> dict[str, Any]:
    active_scans_enabled = _strict_bool("XBOW_ENABLE_ACTIVE_SCANS", False)
    scanner_worker_enabled = _strict_bool("XBOW_ENABLE_SCANNER_WORKER", False)
    nuclei_enabled = _strict_bool("XBOW_ENABLE_NUCLEI", False)
    dry_run = _strict_bool("DRY_RUN", True)
    profile = (os.getenv("XBOW_SCANNER_SANDBOX_PROFILE") or "").strip().lower()
    engines = tuple(
        sorted(
            {
                item.strip().lower()
                for item in os.getenv("XBOW_SCANNER_ALLOWED_ENGINES", "nuclei").split(",")
                if item.strip()
            }
        )
    )
    supported_engines = {"nuclei", "strix"}
    unsupported_engines = [item for item in engines if item not in supported_engines]
    nuclei_allowlisted = "nuclei" in engines
    nuclei_version_configured = bool(
        (os.getenv("XBOW_NUCLEI_ALLOWED_VERSION") or "").strip()
    )
    nuclei_execution_intent = bool(
        active_scans_enabled and nuclei_enabled and not dry_run
    )

    reasons: list[str] = []
    if not active_scans_enabled:
        reasons.append("active_scans_disabled")
    if dry_run:
        reasons.append("global_dry_run")
    if not scanner_worker_enabled:
        reasons.append("scanner_worker_disabled")
    if profile != "restricted-v1":
        reasons.append("restricted_sandbox_profile_required")
    if not engines:
        reasons.append("no_scanner_engine_allowlisted")
    if unsupported_engines:
        reasons.append("unsupported_scanner_engine")
    if nuclei_execution_intent and not nuclei_allowlisted:
        reasons.append("nuclei_not_allowlisted")
    if nuclei_execution_intent and not nuclei_version_configured:
        reasons.append("nuclei_version_allowlist_missing")

    return {
        "mode": "active_gated" if active_scans_enabled else "disabled",
        "active_scans_enabled": active_scans_enabled,
        "scanner_worker_enabled": scanner_worker_enabled,
        "nuclei_enabled": nuclei_enabled,
        "nuclei_execution_intent": nuclei_execution_intent,
        "nuclei_allowlisted": nuclei_allowlisted,
        "nuclei_version_configured": nuclei_version_configured,
        "dry_run": dry_run,
        "sandbox_profile": profile or "unconfigured",
        "allowed_engines": list(engines),
        "dispatch_ready": not reasons,
        "dispatch_block_reasons": reasons,
        "worker_admission_enforced": True,
        "contains_secrets": False,
    }


def safe_scanner_runtime_capability() -> dict[str, Any]:
    try:
        return scanner_runtime_capability()
    except CapabilityConfigError:
        return {
            "mode": "configuration_error",
            "active_scans_enabled": False,
            "scanner_worker_enabled": False,
            "nuclei_enabled": False,
            "nuclei_execution_intent": False,
            "nuclei_allowlisted": False,
            "nuclei_version_configured": False,
            "dry_run": True,
            "sandbox_profile": "configuration_error",
            "allowed_engines": [],
            "dispatch_ready": False,
            "dispatch_block_reasons": ["invalid_boolean_configuration"],
            "worker_admission_enforced": True,
            "contains_secrets": False,
            "configuration_error": True,
        }
