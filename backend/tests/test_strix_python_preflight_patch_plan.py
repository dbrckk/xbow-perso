from __future__ import annotations

import pytest

from app.strix_python_preflight_patch_plan import (
    STRIX_PYTHON_PREFLIGHT_PATCH_PLAN_SCHEMA,
    StrixPythonPreflightPatchPlanError,
    build_preflight_patch_plan,
)


def _surface() -> dict:
    return {
        "schema": "strix-python-preflight-surface-v1",
        "patch_symbols": [
            "check_docker_installed",
            "pull_docker_image",
        ],
        "preserved_symbols": ["validate_environment"],
        "direct_import_identity_verified": True,
        "mutation_performed": False,
        "patch_application_enabled": False,
        "entrypoint_called": False,
        "active_execution_enabled": False,
    }


def test_patch_plan_is_inert_and_exact():
    result = build_preflight_patch_plan(_surface())

    assert result == {
        "schema": STRIX_PYTHON_PREFLIGHT_PATCH_PLAN_SCHEMA,
        "target_module": "strix.interface.main",
        "replacement_symbols": [
            "check_docker_installed",
            "pull_docker_image",
        ],
        "preserved_symbols": ["validate_environment"],
        "replacement_behavior": "verified_noop_preflight_only",
        "mutation_performed": False,
        "patch_application_enabled": False,
        "entrypoint_called": False,
        "active_execution_enabled": False,
    }


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update(mutation_performed=True),
        lambda value: value.update(patch_application_enabled=True),
        lambda value: value.update(entrypoint_called=True),
        lambda value: value.update(active_execution_enabled=True),
        lambda value: value.update(
            patch_symbols=["check_docker_installed"],
        ),
        lambda value: value.update(
            preserved_symbols=["other_validation"],
        ),
    ),
)
def test_patch_plan_rejects_unsafe_surface(mutate):
    surface = _surface()
    mutate(surface)

    with pytest.raises(StrixPythonPreflightPatchPlanError):
        build_preflight_patch_plan(surface)


def test_patch_plan_rejects_unknown_surface_fields():
    surface = _surface()
    surface["unexpected"] = True

    with pytest.raises(
        StrixPythonPreflightPatchPlanError,
        match="surface contract",
    ):
        build_preflight_patch_plan(surface)
