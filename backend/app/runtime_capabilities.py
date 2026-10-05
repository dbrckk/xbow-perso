from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .scanner_sandbox import strix_runtime_contract_enforceable
from .strix_execution_contract import STRIX_EXECUTION_CONTRACT_SCHEMA
from .strix_runner_rpc import RUNNER_RPC_PROTOCOL


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
    strix_allowlisted = "strix" in engines
    strix_execution_intent = bool(
        active_scans_enabled and strix_allowlisted and not dry_run
    )
    strix_binary_available = bool(shutil.which("strix"))
    docker_cli_available = bool(shutil.which("docker"))
    strix_contract_enforceable = strix_runtime_contract_enforceable()
    strix_python_bootstrap_ready = False
    strix_upstream_docker_preflight_required = True

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
    if strix_execution_intent and not strix_binary_available:
        reasons.append("strix_binary_unavailable")
    if strix_execution_intent and not docker_cli_available:
        reasons.append("strix_docker_runtime_unavailable")
    if strix_execution_intent and not strix_contract_enforceable:
        reasons.append("strix_runtime_contract_not_enforceable")
    if strix_execution_intent:
        reasons.append("strix_runner_rpc_execution_not_implemented")
        reasons.append("strix_backend_hook_not_loaded_by_standalone_binary")
        if not strix_python_bootstrap_ready:
            reasons.append("strix_python_bootstrap_not_ready")
        if strix_upstream_docker_preflight_required:
            reasons.append("strix_upstream_docker_preflight_required")

    return {
        "mode": "active_gated" if active_scans_enabled else "disabled",
        "active_scans_enabled": active_scans_enabled,
        "scanner_worker_enabled": scanner_worker_enabled,
        "nuclei_enabled": nuclei_enabled,
        "nuclei_execution_intent": nuclei_execution_intent,
        "nuclei_allowlisted": nuclei_allowlisted,
        "nuclei_version_configured": nuclei_version_configured,
        "strix_execution_intent": strix_execution_intent,
        "strix_allowlisted": strix_allowlisted,
        "strix_binary_available": strix_binary_available,
        "strix_docker_runtime_available": docker_cli_available,
        "strix_runtime_contract_enforceable": strix_contract_enforceable,
        "strix_execution_contract_schema": STRIX_EXECUTION_CONTRACT_SCHEMA,
        "strix_execution_contract_required": True,
        "strix_broker_mode": "read_only_http_boundary",
        "strix_broker_read_only_egress_available": True,
        "strix_broker_egress_enforced": False,
        "strix_broker_internal_network_required": True,
        "strix_broker_allowed_methods": ["GET", "HEAD"],
        "strix_broker_public_network_only": True,
        "strix_broker_dns_pinning": True,
        "strix_broker_redirects_followed": False,
        "strix_runner_network_isolated": False,
        "strix_runner_network_isolation_ci_verified": True,
        "strix_runner_rpc_protocol": RUNNER_RPC_PROTOCOL,
        "strix_runner_rpc_contract_defined": True,
        "strix_runner_rpc_execution_implemented": False,
        "strix_command_admission_contract_defined": True,
        "strix_command_profiles": ["bootstrap-v1", "web-active-v1"],
        "strix_command_shell_interpreters_allowed": False,
        "strix_command_direct_egress_allowed": False,
        "strix_command_network_scope_enforcement": "broker_required",
        "strix_command_admission_enforced": False,
        "strix_backend_hook_loaded_by_standalone_binary": False,
        "strix_python_bootstrap_ready": strix_python_bootstrap_ready,
        "strix_python_bootstrap_plan_contract_defined": True,
        "strix_python_bootstrap_runtime_contract_defined": True,
        "strix_python_bootstrap_backend_first_import_enforced": True,
        "strix_python_bootstrap_entrypoint_enabled": False,
        "strix_python_preflight_patch_plan_contract_defined": True,
        "strix_python_preflight_compatibility_contract_defined": True,
        "strix_python_preflight_patch_application_supported": True,
        "strix_python_preflight_patch_application_enabled": False,
        "strix_python_preflight_compatibility_applied": False,
        "strix_python_preflight_preserves_environment_validation": True,
        "strix_upstream_docker_preflight_required": (
            strix_upstream_docker_preflight_required
        ),
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
            "strix_execution_intent": False,
            "strix_allowlisted": False,
            "strix_binary_available": False,
            "strix_docker_runtime_available": False,
            "strix_runtime_contract_enforceable": False,
            "strix_execution_contract_schema": STRIX_EXECUTION_CONTRACT_SCHEMA,
            "strix_execution_contract_required": True,
            "strix_broker_mode": "read_only_http_boundary",
            "strix_broker_read_only_egress_available": True,
            "strix_broker_egress_enforced": False,
            "strix_broker_internal_network_required": True,
            "strix_broker_allowed_methods": ["GET", "HEAD"],
            "strix_broker_public_network_only": True,
            "strix_broker_dns_pinning": True,
            "strix_broker_redirects_followed": False,
            "strix_runner_network_isolated": False,
            "strix_runner_network_isolation_ci_verified": True,
            "strix_runner_rpc_protocol": RUNNER_RPC_PROTOCOL,
            "strix_runner_rpc_contract_defined": True,
            "strix_runner_rpc_execution_implemented": False,
            "strix_command_admission_contract_defined": True,
            "strix_command_profiles": ["bootstrap-v1", "web-active-v1"],
            "strix_command_shell_interpreters_allowed": False,
            "strix_command_direct_egress_allowed": False,
            "strix_command_network_scope_enforcement": "broker_required",
            "strix_command_admission_enforced": False,
            "strix_backend_hook_loaded_by_standalone_binary": False,
            "strix_python_bootstrap_ready": False,
            "strix_python_bootstrap_plan_contract_defined": True,
            "strix_python_bootstrap_runtime_contract_defined": True,
            "strix_python_bootstrap_backend_first_import_enforced": True,
            "strix_python_bootstrap_entrypoint_enabled": False,
            "strix_python_preflight_patch_plan_contract_defined": True,
            "strix_python_preflight_compatibility_contract_defined": True,
            "strix_python_preflight_patch_application_supported": True,
            "strix_python_preflight_patch_application_enabled": False,
            "strix_python_preflight_compatibility_applied": False,
            "strix_python_preflight_preserves_environment_validation": True,
            "strix_upstream_docker_preflight_required": True,
            "dry_run": True,
            "sandbox_profile": "configuration_error",
            "allowed_engines": [],
            "dispatch_ready": False,
            "dispatch_block_reasons": ["invalid_boolean_configuration"],
            "worker_admission_enforced": True,
            "contains_secrets": False,
            "configuration_error": True,
        }



def browser_runtime_capability() -> dict[str, Any]:
    """Return redacted readiness for bounded browser observation."""
    enabled = _strict_bool("XBOW_ENABLE_BROWSER_AUTOMATION", False)
    marker = Path(
        os.getenv("XBOW_PLAYWRIGHT_RUNTIME_MARKER", "/opt/xbow-playwright-ready")
    )
    runtime_attested = marker.is_file()

    reasons: list[str] = []
    if not enabled:
        reasons.append("browser_automation_disabled")
    if enabled and not runtime_attested:
        reasons.append("playwright_runtime_unattested")

    return {
        "mode": "enabled" if enabled else "disabled",
        "browser_automation_enabled": enabled,
        "playwright_runtime_attested": runtime_attested,
        "dispatch_ready": not reasons,
        "dispatch_block_reasons": reasons,
        "contains_secrets": False,
    }


def safe_browser_runtime_capability() -> dict[str, Any]:
    try:
        return browser_runtime_capability()
    except CapabilityConfigError:
        return {
            "mode": "configuration_error",
            "browser_automation_enabled": False,
            "playwright_runtime_attested": False,
            "dispatch_ready": False,
            "dispatch_block_reasons": ["invalid_boolean_configuration"],
            "contains_secrets": False,
            "configuration_error": True,
        }


def recon_runtime_capability() -> dict[str, Any]:
    """Return a redacted preflight for the bounded recon execution path."""
    recon_enabled = _strict_bool("XBOW_ENABLE_RECON", False)
    external_enabled = _strict_bool("XBOW_ENABLE_EXTERNAL_RECON", False)
    required_tools = ("katana", "httpx", "subfinder")
    available_tools = {
        name: bool(shutil.which(name))
        for name in required_tools
    }

    reasons: list[str] = []
    if not recon_enabled:
        reasons.append("recon_disabled")
    if external_enabled:
        missing = [
            name
            for name, available in available_tools.items()
            if not available
        ]
        reasons.extend(f"{name}_unavailable" for name in missing)

    return {
        "mode": (
            "external_gated"
            if external_enabled
            else ("builtin_only" if recon_enabled else "disabled")
        ),
        "recon_enabled": recon_enabled,
        "external_recon_enabled": external_enabled,
        "tools": available_tools,
        "dispatch_ready": not reasons,
        "dispatch_block_reasons": reasons,
        "scope_revalidation": True,
        "read_only_default": True,
        "contains_secrets": False,
    }


def safe_recon_runtime_capability() -> dict[str, Any]:
    try:
        return recon_runtime_capability()
    except CapabilityConfigError:
        return {
            "mode": "configuration_error",
            "recon_enabled": False,
            "external_recon_enabled": False,
            "tools": {
                "katana": False,
                "httpx": False,
                "subfinder": False,
            },
            "dispatch_ready": False,
            "dispatch_block_reasons": ["invalid_boolean_configuration"],
            "scope_revalidation": True,
            "read_only_default": True,
            "contains_secrets": False,
            "configuration_error": True,
        }
