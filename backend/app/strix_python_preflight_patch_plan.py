from __future__ import annotations

from typing import Any

from .strix_python_preflight_surface import (
    STRIX_PYTHON_PREFLIGHT_SURFACE_SCHEMA,
)


STRIX_PYTHON_PREFLIGHT_PATCH_PLAN_SCHEMA = (
    "strix-python-preflight-patch-plan-v1"
)
_PATCH_SYMBOLS = [
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


class StrixPythonPreflightPatchPlanError(RuntimeError):
    pass


def _verify_surface(surface: dict[str, Any]) -> None:
    if set(surface) != _SURFACE_KEYS:
        raise StrixPythonPreflightPatchPlanError(
            "preflight surface contract changed"
        )
    if (
        surface.get("schema") != STRIX_PYTHON_PREFLIGHT_SURFACE_SCHEMA
        or surface.get("patch_symbols") != _PATCH_SYMBOLS
        or surface.get("preserved_symbols") != _PRESERVED_SYMBOLS
        or surface.get("direct_import_identity_verified") is not True
        or surface.get("mutation_performed") is not False
        or surface.get("patch_application_enabled") is not False
        or surface.get("entrypoint_called") is not False
        or surface.get("active_execution_enabled") is not False
    ):
        raise StrixPythonPreflightPatchPlanError(
            "preflight surface is not safely inert"
        )


def build_preflight_patch_plan(
    surface: dict[str, Any],
) -> dict[str, Any]:
    _verify_surface(surface)
    return {
        "schema": STRIX_PYTHON_PREFLIGHT_PATCH_PLAN_SCHEMA,
        "target_module": "strix.interface.main",
        "replacement_symbols": list(_PATCH_SYMBOLS),
        "preserved_symbols": list(_PRESERVED_SYMBOLS),
        "replacement_behavior": "verified_noop_preflight_only",
        "mutation_performed": False,
        "patch_application_enabled": False,
        "entrypoint_called": False,
        "active_execution_enabled": False,
    }
