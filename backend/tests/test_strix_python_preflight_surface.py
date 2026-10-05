from __future__ import annotations

import pytest

from app.strix_python_preflight_surface import (
    STRIX_PYTHON_PREFLIGHT_SURFACE_SCHEMA,
    StrixPythonPreflightSurfaceError,
    inspect_preflight_surface,
)


def _plan() -> dict:
    return {
        "schema": "strix-python-bootstrap-plan-v1",
        "strix_version": "1.6.2",
        "source_commit": "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2",
        "backend": "xbow-remote-v1",
        "python_version": "3.12.14",
        "uv_version": "0.12.10",
        "architecture": "amd64",
        "source_attested": True,
        "dependency_lock_attested": True,
        "toolchain_attested": True,
        "docker_preflight_patch_symbols": [
            "check_docker_installed",
            "pull_docker_image",
        ],
        "preserved_validation_symbol": "validate_environment",
        "preflight_call_order_verified": True,
        "host_docker_socket_required": False,
        "patch_application_enabled": False,
        "entrypoint_enabled": False,
        "active_execution_enabled": False,
    }


def test_preflight_surface_verifies_direct_import_identity():
    def check_docker_installed():
        return None

    def pull_docker_image():
        return None

    def validate_environment():
        return None

    environment = {
        "check_docker_installed": check_docker_installed,
        "pull_docker_image": pull_docker_image,
        "validate_environment": validate_environment,
    }
    main = dict(environment)

    result = inspect_preflight_surface(
        main_namespace=main,
        environment_namespace=environment,
        bootstrap_plan=_plan(),
    )

    assert result == {
        "schema": STRIX_PYTHON_PREFLIGHT_SURFACE_SCHEMA,
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


def test_preflight_surface_rejects_validation_rebinding():
    def check_docker_installed():
        return None

    def pull_docker_image():
        return None

    def validate_environment():
        return None

    def rebound_validation():
        return None

    environment = {
        "check_docker_installed": check_docker_installed,
        "pull_docker_image": pull_docker_image,
        "validate_environment": validate_environment,
    }
    main = {
        **environment,
        "validate_environment": rebound_validation,
    }

    with pytest.raises(
        StrixPythonPreflightSurfaceError,
        match="identity",
    ):
        inspect_preflight_surface(
            main_namespace=main,
            environment_namespace=environment,
            bootstrap_plan=_plan(),
        )


def test_preflight_surface_rejects_patch_symbol_rebinding():
    def check_docker_installed():
        return None

    def alternate_check():
        return None

    def pull_docker_image():
        return None

    def validate_environment():
        return None

    environment = {
        "check_docker_installed": check_docker_installed,
        "pull_docker_image": pull_docker_image,
        "validate_environment": validate_environment,
    }
    main = {
        **environment,
        "check_docker_installed": alternate_check,
    }

    with pytest.raises(
        StrixPythonPreflightSurfaceError,
        match="identity",
    ):
        inspect_preflight_surface(
            main_namespace=main,
            environment_namespace=environment,
            bootstrap_plan=_plan(),
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda plan: plan.update(patch_application_enabled=True),
        lambda plan: plan.update(entrypoint_enabled=True),
        lambda plan: plan.update(active_execution_enabled=True),
        lambda plan: plan.update(host_docker_socket_required=True),
        lambda plan: plan.update(
            preserved_validation_symbol="other_validation",
        ),
    ),
)
def test_preflight_surface_rejects_unsafe_plan(mutate):
    plan = _plan()
    mutate(plan)

    with pytest.raises(StrixPythonPreflightSurfaceError):
        inspect_preflight_surface(
            main_namespace={},
            environment_namespace={},
            bootstrap_plan=plan,
        )


def test_preflight_surface_rejects_unknown_plan_fields():
    plan = _plan()
    plan["unexpected"] = True

    with pytest.raises(
        StrixPythonPreflightSurfaceError,
        match="plan contract",
    ):
        inspect_preflight_surface(
            main_namespace={},
            environment_namespace={},
            bootstrap_plan=plan,
        )
