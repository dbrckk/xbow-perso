from __future__ import annotations

import pytest

from app.strix_python_preflight_shim import (
    STRIX_PYTHON_PREFLIGHT_SHIM_SCHEMA,
    StrixPythonPreflightShimError,
    build_preflight_shim_contract,
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


def test_preflight_shim_contract_is_non_executable():
    result = build_preflight_shim_contract(_surface())

    assert result == {
        "schema": STRIX_PYTHON_PREFLIGHT_SHIM_SCHEMA,
        "replacement_symbols": [
            "check_docker_installed",
            "pull_docker_image",
        ],
        "replacement_behavior": "future-noop",
        "preserved_symbols": ["validate_environment"],
        "surface_identity_verified": True,
        "replacement_callables_exposed": False,
        "module_mutation_enabled": False,
        "entrypoint_enabled": False,
        "active_execution_enabled": False,
    }


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update(
            patch_symbols=["check_docker_installed"],
        ),
        lambda value: value.update(
            preserved_symbols=["other_validation"],
        ),
        lambda value: value.update(
            direct_import_identity_verified=False,
        ),
        lambda value: value.update(mutation_performed=True),
        lambda value: value.update(patch_application_enabled=True),
        lambda value: value.update(entrypoint_called=True),
        lambda value: value.update(active_execution_enabled=True),
    ),
)
def test_preflight_shim_contract_rejects_unsafe_surface(mutate):
    surface = _surface()
    mutate(surface)

    with pytest.raises(StrixPythonPreflightShimError):
        build_preflight_shim_contract(surface)


def test_preflight_shim_contract_rejects_unknown_surface_fields():
    surface = _surface()
    surface["unexpected"] = True

    with pytest.raises(
        StrixPythonPreflightShimError,
        match="surface contract",
    ):
        build_preflight_shim_contract(surface)
