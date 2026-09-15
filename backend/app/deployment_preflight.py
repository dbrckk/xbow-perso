from __future__ import annotations

import os
from typing import Any

from .runtime_capabilities import safe_pentagi_runtime_capability


def _configured(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _bool_env(name: str, default: bool = False) -> tuple[bool, bool]:
    raw = os.getenv(name)
    if raw is None:
        return default, True
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True, True
    if value in {"0", "false", "no", "off"}:
        return False, True
    return default, False


def build_deployment_preflight(
    dependencies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return redacted deployment diagnostics without changing runtime state."""

    pentagi = safe_pentagi_runtime_capability()
    issues: list[dict[str, Any]] = []
    legacy_provenance_mode, provenance_flag_valid = _bool_env(
        "XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS",
        False,
    )

    if not provenance_flag_valid:
        issues.append(
            {
                "code": "invalid_legacy_provenance_flag",
                "severity": "error",
                "component": "job_provenance",
            }
        )
    elif legacy_provenance_mode:
        issues.append(
            {
                "code": "legacy_unprovenanced_jobs_enabled",
                "severity": "warning",
                "component": "job_provenance",
            }
        )

    if dependencies is not None and not bool(dependencies.get("ok")):
        issues.append(
            {
                "code": "dependencies_not_ready",
                "severity": "error",
                "component": "core",
            }
        )

    if pentagi.get("mode") == "configuration_error":
        issues.append(
            {
                "code": "pentagi_invalid_boolean_configuration",
                "severity": "error",
                "component": "pentagi",
            }
        )

    integration_enabled = bool(pentagi.get("integration_enabled"))
    worker_enabled = bool(pentagi.get("worker_enabled"))
    transport_enabled = bool(pentagi.get("transport_enabled"))
    status_worker_enabled = bool(
        (pentagi.get("status_tracking") or {}).get("worker_enabled")
    )

    if integration_enabled:
        if not _configured("XBOW_PENTAGI_BASE_URL"):
            issues.append(
                {
                    "code": "pentagi_base_url_missing",
                    "severity": "error",
                    "component": "pentagi",
                }
            )
        if not _configured("XBOW_PENTAGI_MODEL_PROVIDER"):
            issues.append(
                {
                    "code": "pentagi_model_provider_missing",
                    "severity": "error",
                    "component": "pentagi",
                }
            )

    if worker_enabled and not integration_enabled:
        issues.append(
            {
                "code": "pentagi_worker_enabled_without_integration",
                "severity": "warning",
                "component": "pentagi",
            }
        )
    if transport_enabled and not integration_enabled:
        issues.append(
            {
                "code": "pentagi_transport_enabled_without_integration",
                "severity": "warning",
                "component": "pentagi",
            }
        )
    if status_worker_enabled and not integration_enabled:
        issues.append(
            {
                "code": "pentagi_status_worker_enabled_without_integration",
                "severity": "warning",
                "component": "pentagi",
            }
        )

    execution_intent = bool(
        integration_enabled
        and pentagi.get("active_scans_enabled")
        and not pentagi.get("dry_run", True)
        and worker_enabled
        and transport_enabled
    )
    if execution_intent and not pentagi.get("execution_transport_enforceable"):
        issues.append(
            {
                "code": "pentagi_execution_intent_not_enforceable",
                "severity": "warning",
                "component": "pentagi",
            }
        )

    severities = {str(item["severity"]) for item in issues}
    if "error" in severities:
        status = "error"
    elif "warning" in severities:
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "issues": issues,
        "dependencies_ready": (
            bool(dependencies.get("ok"))
            if dependencies is not None
            else None
        ),
        "job_provenance": {
            "strict_by_default": True,
            "legacy_unprovenanced_jobs_enabled": legacy_provenance_mode,
            "configuration_valid": provenance_flag_valid,
            "schema": "job-provenance-v1",
        },
        "pentagi": {
            "mode": pentagi.get("mode"),
            "dispatch_ready": bool(pentagi.get("dispatch_ready")),
            "execution_transport_enforceable": bool(
                pentagi.get("execution_transport_enforceable")
            ),
            "base_url_configured": _configured("XBOW_PENTAGI_BASE_URL"),
            "model_provider_configured": _configured(
                "XBOW_PENTAGI_MODEL_PROVIDER"
            ),
        },
        "read_only": True,
        "contains_secrets": False,
        "contains_endpoint_values": False,
    }
