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
