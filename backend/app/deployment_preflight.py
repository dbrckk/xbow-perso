from __future__ import annotations

import os
from typing import Any

from .runtime_capabilities import (
    safe_pentagi_runtime_capability,
    safe_scanner_runtime_capability,
)


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


def _production_mode() -> bool:
    return (os.getenv("XBOW_DEPLOYMENT_ENV") or "").strip().lower() == "production"


def _image_digest_configured(name: str) -> bool:
    value = (os.getenv(name) or "").strip()
    if not value:
        return False
    return "@sha256:" in value and len(value.rsplit("@sha256:", 1)[-1]) == 64


def build_deployment_preflight(
    dependencies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return redacted deployment diagnostics without changing runtime state."""

    pentagi = safe_pentagi_runtime_capability()
    scanner = safe_scanner_runtime_capability()
    issues: list[dict[str, Any]] = []
    production = _production_mode()
    legacy_jobs_enabled, legacy_jobs_valid = _bool_env(
        "XBOW_ALLOW_LEGACY_UNPROVENANCED_JOBS"
    )

    if not legacy_jobs_valid:
        issues.append(
            {
                "code": "invalid_legacy_provenance_flag",
                "severity": "error",
                "component": "job_provenance",
            }
        )
    elif legacy_jobs_enabled:
        issues.append(
            {
                "code": "legacy_unprovenanced_jobs_enabled",
                "severity": "warning",
                "component": "job_provenance",
            }
        )

    storage_backend = (os.getenv("XBOW_STORAGE_BACKEND") or "sqlite").strip().lower()
    queue_backend = (os.getenv("XBOW_QUEUE_BACKEND") or "sqlite").strip().lower()
    rate_limit_enabled, rate_limit_valid = _bool_env("XBOW_API_RATE_LIMIT_ENABLED")
    rate_limit_backend = (
        os.getenv("XBOW_API_RATE_LIMIT_BACKEND") or "memory"
    ).strip().lower()
    vault_enabled, vault_valid = _bool_env("XBOW_VAULT_ENABLED")
    vault_key_file_configured = _configured("XBOW_VAULT_MASTER_KEY_FILE")
    vault_inline_key_configured = _configured("XBOW_VAULT_MASTER_KEY")

    if production:
        for env_name, code in (
            ("XBOW_BACKEND_IMAGE", "backend_image_digest_missing"),
            ("XBOW_FRONTEND_IMAGE", "frontend_image_digest_missing"),
        ):
            if not _image_digest_configured(env_name):
                issues.append(
                    {
                        "code": code,
                        "severity": "error",
                        "component": "supply_chain",
                    }
                )

        if storage_backend not in {"postgres", "postgresql"}:
            issues.append(
                {
                    "code": "production_postgresql_required",
                    "severity": "error",
                    "component": "storage",
                }
            )
        if queue_backend != "redis":
            issues.append(
                {
                    "code": "production_redis_queue_required",
                    "severity": "error",
                    "component": "queue",
                }
            )
        if not rate_limit_valid:
            issues.append(
                {
                    "code": "invalid_api_rate_limit_flag",
                    "severity": "error",
                    "component": "api_rate_limit",
                }
            )
        elif not rate_limit_enabled or rate_limit_backend != "redis":
            issues.append(
                {
                    "code": "production_redis_rate_limit_required",
                    "severity": "error",
                    "component": "api_rate_limit",
                }
            )
        if not vault_valid:
            issues.append(
                {
                    "code": "invalid_vault_enabled_flag",
                    "severity": "error",
                    "component": "vault",
                }
            )
        elif not vault_enabled:
            issues.append(
                {
                    "code": "production_vault_required",
                    "severity": "error",
                    "component": "vault",
                }
            )
        elif not vault_key_file_configured:
            issues.append(
                {
                    "code": "production_vault_key_file_required",
                    "severity": "error",
                    "component": "vault",
                }
            )
        if vault_inline_key_configured:
            issues.append(
                {
                    "code": "production_inline_vault_key_forbidden",
                    "severity": "error",
                    "component": "vault",
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

    if scanner.get("mode") == "configuration_error":
        issues.append(
            {
                "code": "scanner_invalid_boolean_configuration",
                "severity": "error",
                "component": "scanner",
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

    scanner_execution_intent = bool(scanner.get("nuclei_execution_intent"))
    if scanner_execution_intent and scanner.get("mode") != "configuration_error":
        if not scanner.get("scanner_worker_enabled"):
            issues.append(
                {
                    "code": "scanner_worker_disabled",
                    "severity": "error",
                    "component": "scanner",
                }
            )
        if scanner.get("sandbox_profile") != "restricted-v1":
            issues.append(
                {
                    "code": "scanner_sandbox_profile_required",
                    "severity": "error",
                    "component": "scanner",
                }
            )
        if not scanner.get("nuclei_allowlisted"):
            issues.append(
                {
                    "code": "nuclei_not_allowlisted",
                    "severity": "error",
                    "component": "scanner",
                }
            )
        if not scanner.get("nuclei_version_configured"):
            issues.append(
                {
                    "code": "nuclei_version_allowlist_missing",
                    "severity": "error",
                    "component": "scanner",
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
        "deployment_integrity": {
            "production_mode": production,
            "backend_image_digest_configured": _image_digest_configured("XBOW_BACKEND_IMAGE"),
            "frontend_image_digest_configured": _image_digest_configured("XBOW_FRONTEND_IMAGE"),
            "storage_backend": storage_backend,
            "queue_backend": queue_backend,
            "api_rate_limit_enabled": rate_limit_enabled,
            "api_rate_limit_configuration_valid": rate_limit_valid,
            "api_rate_limit_backend": rate_limit_backend,
            "vault_enabled": vault_enabled,
            "vault_configuration_valid": vault_valid,
            "vault_master_key_file_configured": vault_key_file_configured,
            "vault_inline_key_configured": vault_inline_key_configured,
        },
        "dependencies_ready": (
            bool(dependencies.get("ok"))
            if dependencies is not None
            else None
        ),
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
        "scanner": {
            "execution_intent": scanner_execution_intent,
            "nuclei_enabled": bool(scanner.get("nuclei_enabled")),
            "worker_enabled": bool(scanner.get("scanner_worker_enabled")),
            "sandbox_profile": scanner.get("sandbox_profile"),
            "nuclei_allowlisted": bool(scanner.get("nuclei_allowlisted")),
            "nuclei_version_configured": bool(
                scanner.get("nuclei_version_configured")
            ),
            "dispatch_ready": bool(scanner.get("dispatch_ready")),
        },
        "job_provenance": {
            "strict_by_default": True,
            "legacy_unprovenanced_jobs_enabled": legacy_jobs_enabled,
            "configuration_valid": legacy_jobs_valid,
            "schema": "job-provenance-v1",
        },
        "read_only": True,
        "contains_secrets": False,
        "contains_endpoint_values": False,
    }
