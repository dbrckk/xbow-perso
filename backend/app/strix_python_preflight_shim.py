from __future__ import annotations

from typing import Any

from .strix_python_preflight_surface import (
    STRIX_PYTHON_PREFLIGHT_SURFACE_SCHEMA,
)


STRIX_PYTHON_PREFLIGHT_SHIM_SCHEMA = "strix-python-preflight-shim-v1"
_REPLACEMENT_SYMBOLS = [
    "check_docker_installed",
    "pull_docker_image",
]
_PRESERVED_SYMBOLS = ["validate_environment"]
_SURFACE_KEYS = {
    "schema",
    "patch_symbols",
    "preserved_symbols",
    "direct_import_identity_verified",
    "mutation_performed",
    "patch_application_enabled",
    "entrypoint_called",
    "active_execution_enabled",
}


class StrixPythonPreflightShimError(RuntimeError):
    pass


def _verify_surface(surface: dict[str, Any]) -> None:
    if set(surface) != _SURFACE_KEYS:
        raise StrixPythonPreflightShimError(
            "preflight surface contract changed"
        )
    if (
        surface.get("schema") != STRIX_PYTHON_PREFLIGHT_SURFACE_SCHEMA
        or surface.get("patch_symbols") != _REPLACEMENT_SYMBOLS
        or surface.get("preserved_symbols") != _PRESERVED_SYMBOLS
        or surface.get("direct_import_identity_verified") is not True
        or surface.get("mutation_performed") is not False
        or surface.get("patch_application_enabled") is not False
        or surface.get("entrypoint_called") is not False
        or surface.get("active_execution_enabled") is not False
    ):
        raise StrixPythonPreflightShimError(
            "preflight surface is not safely inert"
        )


def build_preflight_shim_contract(
    surface: dict[str, Any],
) -> dict[str, Any]:
    _verify_surface(surface)

    return {
        "schema": STRIX_PYTHON_PREFLIGHT_SHIM_SCHEMA,
        "replacement_symbols": list(_REPLACEMENT_SYMBOLS),
        "replacement_behavior": "future-noop",
        "preserved_symbols": list(_PRESERVED_SYMBOLS),
        "surface_identity_verified": True,
        "replacement_callables_exposed": False,
        "module_mutation_enabled": False,
        "entrypoint_enabled": False,
        "active_execution_enabled": False,
    }
