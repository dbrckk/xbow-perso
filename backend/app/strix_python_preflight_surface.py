from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .strix_backend_hook import STRIX_BACKEND_NAME
from .strix_python_bootstrap_plan import (
    STRIX_PYTHON_BOOTSTRAP_PLAN_SCHEMA,
)
from .strix_python_lock_probe import (
    STRIX_SOURCE_COMMIT,
    STRIX_VERSION,
)
from .strix_python_toolchain_probe import (
    STRIX_RELEASE_PYTHON_VERSION,
    STRIX_RELEASE_UV_VERSION,
)


STRIX_PYTHON_PREFLIGHT_SURFACE_SCHEMA = (
    "strix-python-preflight-surface-v1"
)
_PATCH_SYMBOLS = [
    "check_docker_installed",
    "pull_docker_image",
]
_PRESERVED_SYMBOL = "validate_environment"
_PLAN_KEYS = {
    "schema",
    "strix_version",
    "source_commit",
    "backend",
    "python_version",
    "uv_version",
    "architecture",
    "source_attested",
    "dependency_lock_attested",
    "toolchain_attested",
    "docker_preflight_patch_symbols",
    "preserved_validation_symbol",
    "preflight_call_order_verified",
    "host_docker_socket_required",
    "patch_application_enabled",
    "entrypoint_enabled",
    "active_execution_enabled",
}


class StrixPythonPreflightSurfaceError(RuntimeError):
    pass


def _verify_plan(plan: dict[str, Any]) -> None:
    if set(plan) != _PLAN_KEYS:
        raise StrixPythonPreflightSurfaceError(
            "bootstrap plan contract changed"
        )
    if (
        plan.get("schema") != STRIX_PYTHON_BOOTSTRAP_PLAN_SCHEMA
        or plan.get("strix_version") != STRIX_VERSION
        or plan.get("source_commit") != STRIX_SOURCE_COMMIT
        or plan.get("backend") != STRIX_BACKEND_NAME
        or plan.get("python_version") != STRIX_RELEASE_PYTHON_VERSION
        or plan.get("uv_version") != STRIX_RELEASE_UV_VERSION
        or plan.get("source_attested") is not True
        or plan.get("dependency_lock_attested") is not True
        or plan.get("toolchain_attested") is not True
        or plan.get("docker_preflight_patch_symbols")
        != _PATCH_SYMBOLS
        or plan.get("preserved_validation_symbol") != _PRESERVED_SYMBOL
        or plan.get("preflight_call_order_verified") is not True
        or plan.get("host_docker_socket_required") is not False
        or plan.get("patch_application_enabled") is not False
        or plan.get("entrypoint_enabled") is not False
        or plan.get("active_execution_enabled") is not False
    ):
        raise StrixPythonPreflightSurfaceError(
            "bootstrap plan is not safely inert"
        )


def _require_callable_identity(
    *,
    symbol: str,
    main_namespace: Mapping[str, Any],
    environment_namespace: Mapping[str, Any],
) -> None:
    main_value = main_namespace.get(symbol)
    environment_value = environment_namespace.get(symbol)
    if (
        not callable(main_value)
        or not callable(environment_value)
        or main_value is not environment_value
    ):
        raise StrixPythonPreflightSurfaceError(
            f"preflight symbol identity mismatch: {symbol}"
        )


def inspect_preflight_surface(
    *,
    main_namespace: Mapping[str, Any],
    environment_namespace: Mapping[str, Any],
    bootstrap_plan: dict[str, Any],
) -> dict[str, Any]:
    _verify_plan(bootstrap_plan)

    for symbol in (*_PATCH_SYMBOLS, _PRESERVED_SYMBOL):
        _require_callable_identity(
            symbol=symbol,
            main_namespace=main_namespace,
            environment_namespace=environment_namespace,
        )

    return {
        "schema": STRIX_PYTHON_PREFLIGHT_SURFACE_SCHEMA,
        "patch_symbols": list(_PATCH_SYMBOLS),
        "preserved_symbols": [_PRESERVED_SYMBOL],
        "direct_import_identity_verified": True,
        "mutation_performed": False,
        "patch_application_enabled": False,
        "entrypoint_called": False,
        "active_execution_enabled": False,
    }
