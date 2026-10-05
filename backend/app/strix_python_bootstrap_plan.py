from __future__ import annotations

import re
from typing import Any

from .strix_backend_hook import STRIX_BACKEND_NAME
from .strix_python_compat_probe import (
    STRIX_ENVIRONMENT_PY_GIT_BLOB_SHA1,
    STRIX_MAIN_PY_GIT_BLOB_SHA1,
    STRIX_PYTHON_COMPAT_SCHEMA,
)
from .strix_python_lock_probe import (
    STRIX_PYTHON_LOCK_SCHEMA,
    STRIX_SOURCE_COMMIT,
    STRIX_VERSION,
)
from .strix_python_toolchain_probe import (
    STRIX_PYTHON_TOOLCHAIN_SCHEMA,
    STRIX_RELEASE_PYTHON_VERSION,
    STRIX_RELEASE_UV_VERSION,
)


STRIX_PYTHON_BOOTSTRAP_PLAN_SCHEMA = "strix-python-bootstrap-plan-v1"
_DOCKER_PREFLIGHT_SYMBOLS = [
    "check_docker_installed",
    "pull_docker_image",
]
_PRESERVED_VALIDATION_SYMBOL = "validate_environment"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_COMPAT_KEYS = {
    "schema",
    "strix_version",
    "backend",
    "hook_loaded_in_python_runtime",
    "supports_bind_mounts",
    "active_execution_enabled",
    "upstream_docker_preflight_required",
    "entrypoint_enabled",
    "upstream_main_blob_sha1",
    "upstream_environment_blob_sha1",
    "docker_preflight_symbols",
    "preserved_validation_symbol",
    "preflight_call_order_verified",
}
_LOCK_KEYS = {
    "schema",
    "source_commit",
    "strix_version",
    "python_requirement",
    "uv_lock_version",
    "uv_lock_revision",
    "pyproject_blob_sha1",
    "uv_lock_blob_sha1",
    "direct_dependency_count",
    "dependency_lock_attested",
    "runtime_install_enabled",
}
_TOOLCHAIN_KEYS = {
    "schema",
    "source_commit",
    "strix_version",
    "python_version",
    "uv_version",
    "architecture",
    "uv_asset",
    "uv_sha256",
    "toolchain_attested",
    "runtime_install_enabled",
    "active_execution_enabled",
}


class StrixPythonBootstrapPlanError(RuntimeError):
    pass


def _require_exact_contract(
    descriptor: dict[str, Any],
    expected_keys: set[str],
    name: str,
) -> None:
    if set(descriptor) != expected_keys:
        raise StrixPythonBootstrapPlanError(
            f"{name} attestation contract changed"
        )


def _verify_compatibility(descriptor: dict[str, Any]) -> None:
    _require_exact_contract(descriptor, _COMPAT_KEYS, "compatibility")
    if (
        descriptor.get("schema") != STRIX_PYTHON_COMPAT_SCHEMA
        or descriptor.get("strix_version") != STRIX_VERSION
        or descriptor.get("backend") != STRIX_BACKEND_NAME
        or descriptor.get("hook_loaded_in_python_runtime") is not True
        or descriptor.get("supports_bind_mounts") is not False
        or descriptor.get("active_execution_enabled") is not False
        or descriptor.get("upstream_docker_preflight_required") is not True
        or descriptor.get("entrypoint_enabled") is not False
        or descriptor.get("upstream_main_blob_sha1")
        != STRIX_MAIN_PY_GIT_BLOB_SHA1
        or descriptor.get("upstream_environment_blob_sha1")
        != STRIX_ENVIRONMENT_PY_GIT_BLOB_SHA1
        or descriptor.get("docker_preflight_symbols")
        != _DOCKER_PREFLIGHT_SYMBOLS
        or descriptor.get("preserved_validation_symbol")
        != _PRESERVED_VALIDATION_SYMBOL
        or descriptor.get("preflight_call_order_verified") is not True
    ):
        raise StrixPythonBootstrapPlanError(
            "compatibility attestation mismatch"
        )


def _verify_dependency_lock(descriptor: dict[str, Any]) -> None:
    _require_exact_contract(descriptor, _LOCK_KEYS, "dependency lock")
    if (
        descriptor.get("schema") != STRIX_PYTHON_LOCK_SCHEMA
        or descriptor.get("source_commit") != STRIX_SOURCE_COMMIT
        or descriptor.get("strix_version") != STRIX_VERSION
        or descriptor.get("dependency_lock_attested") is not True
        or descriptor.get("runtime_install_enabled") is not False
    ):
        raise StrixPythonBootstrapPlanError(
            "dependency lock attestation mismatch"
        )


def _verify_toolchain(descriptor: dict[str, Any]) -> None:
    _require_exact_contract(descriptor, _TOOLCHAIN_KEYS, "toolchain")
    uv_sha256 = descriptor.get("uv_sha256")
    if (
        descriptor.get("schema") != STRIX_PYTHON_TOOLCHAIN_SCHEMA
        or descriptor.get("source_commit") != STRIX_SOURCE_COMMIT
        or descriptor.get("strix_version") != STRIX_VERSION
        or descriptor.get("python_version") != STRIX_RELEASE_PYTHON_VERSION
        or descriptor.get("uv_version") != STRIX_RELEASE_UV_VERSION
        or descriptor.get("architecture") not in {"amd64", "arm64"}
        or not isinstance(descriptor.get("uv_asset"), str)
        or not descriptor.get("uv_asset")
        or not isinstance(uv_sha256, str)
        or not _SHA256_RE.fullmatch(uv_sha256)
        or descriptor.get("toolchain_attested") is not True
        or descriptor.get("runtime_install_enabled") is not False
        or descriptor.get("active_execution_enabled") is not False
    ):
        raise StrixPythonBootstrapPlanError(
            "toolchain attestation mismatch"
        )


def build_bootstrap_plan(
    *,
    compatibility: dict[str, Any],
    dependency_lock: dict[str, Any],
    toolchain: dict[str, Any],
) -> dict[str, Any]:
    _verify_compatibility(compatibility)
    _verify_dependency_lock(dependency_lock)
    _verify_toolchain(toolchain)

    return {
        "schema": STRIX_PYTHON_BOOTSTRAP_PLAN_SCHEMA,
        "strix_version": STRIX_VERSION,
        "source_commit": STRIX_SOURCE_COMMIT,
        "backend": STRIX_BACKEND_NAME,
        "python_version": STRIX_RELEASE_PYTHON_VERSION,
        "uv_version": STRIX_RELEASE_UV_VERSION,
        "architecture": toolchain["architecture"],
        "source_attested": True,
        "dependency_lock_attested": True,
        "toolchain_attested": True,
        "docker_preflight_patch_symbols": list(
            _DOCKER_PREFLIGHT_SYMBOLS
        ),
        "preserved_validation_symbol": _PRESERVED_VALIDATION_SYMBOL,
        "preflight_call_order_verified": True,
        "host_docker_socket_required": False,
        "patch_application_enabled": False,
        "entrypoint_enabled": False,
        "active_execution_enabled": False,
    }
