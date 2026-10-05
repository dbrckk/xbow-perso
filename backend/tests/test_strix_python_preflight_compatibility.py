from __future__ import annotations

import pytest

from app.strix_python_preflight_compatibility import (
    STRIX_PYTHON_PREFLIGHT_COMPATIBILITY_SCHEMA,
    StrixPythonPreflightCompatibilityError,
    applied_preflight_compatibility,
)


def _plan() -> dict:
    return {
        "schema": "strix-python-preflight-patch-plan-v1",
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


def _namespaces() -> tuple[dict, dict]:
    def check_docker_installed():
        raise AssertionError("Docker preflight must be bypassed")

    def pull_docker_image():
        raise AssertionError("Docker image pull must be bypassed")

    def validate_environment():
        return "validated"

    environment = {
        "check_docker_installed": check_docker_installed,
        "pull_docker_image": pull_docker_image,
        "validate_environment": validate_environment,
    }
    return dict(environment), environment


def test_compatibility_patches_only_attested_main_aliases_and_restores():
    main, environment = _namespaces()
    original_main = dict(main)
    original_environment = dict(environment)

    with applied_preflight_compatibility(
        main_namespace=main,
        environment_namespace=environment,
        patch_plan=_plan(),
    ) as result:
        assert result == {
            "schema": STRIX_PYTHON_PREFLIGHT_COMPATIBILITY_SCHEMA,
            "target_module": "strix.interface.main",
            "replacement_symbols": [
                "check_docker_installed",
                "pull_docker_image",
            ],
            "replacement_behavior": "verified_noop_preflight_only",
            "mutation_performed": True,
            "patch_application_enabled": True,
            "compatibility_applied": True,
            "environment_module_mutated": False,
            "environment_validation_preserved": True,
            "entrypoint_called": False,
            "active_execution_enabled": False,
        }
        assert main["check_docker_installed"]() is None
        assert main["pull_docker_image"]() is None
        assert main["validate_environment"] is original_main["validate_environment"]
        assert environment == original_environment

    assert main == original_main
    assert environment == original_environment


@pytest.mark.parametrize(
    "mutate",
    (
        lambda plan: plan.update(target_module="strix.interface.environment"),
        lambda plan: plan.update(replacement_symbols=["check_docker_installed"]),
        lambda plan: plan.update(preserved_symbols=["other_validation"]),
        lambda plan: plan.update(patch_application_enabled=True),
        lambda plan: plan.update(entrypoint_called=True),
        lambda plan: plan.update(active_execution_enabled=True),
    ),
)
def test_compatibility_rejects_tampered_patch_plan(mutate):
    main, environment = _namespaces()
    plan = _plan()
    mutate(plan)

    with pytest.raises(StrixPythonPreflightCompatibilityError):
        with applied_preflight_compatibility(
            main_namespace=main,
            environment_namespace=environment,
            patch_plan=plan,
        ):
            pass


def test_compatibility_rejects_unknown_plan_fields():
    main, environment = _namespaces()
    plan = _plan()
    plan["unexpected"] = True

    with pytest.raises(
        StrixPythonPreflightCompatibilityError,
        match="contract changed",
    ):
        with applied_preflight_compatibility(
            main_namespace=main,
            environment_namespace=environment,
            patch_plan=plan,
        ):
            pass


def test_compatibility_rejects_direct_import_identity_mismatch():
    main, environment = _namespaces()

    def alternate_check():
        return None

    main["check_docker_installed"] = alternate_check

    with pytest.raises(
        StrixPythonPreflightCompatibilityError,
        match="identity mismatch",
    ):
        with applied_preflight_compatibility(
            main_namespace=main,
            environment_namespace=environment,
            patch_plan=_plan(),
        ):
            pass


def test_compatibility_restores_patch_symbols_after_body_error():
    main, environment = _namespaces()
    original_main = dict(main)

    with pytest.raises(RuntimeError, match="body failed"):
        with applied_preflight_compatibility(
            main_namespace=main,
            environment_namespace=environment,
            patch_plan=_plan(),
        ):
            raise RuntimeError("body failed")

    assert main == original_main


def test_compatibility_fails_if_validation_is_rebound_during_context():
    main, environment = _namespaces()
    original_main = dict(main)
    original_environment = dict(environment)

    def alternate_validation():
        return None

    with pytest.raises(
        StrixPythonPreflightCompatibilityError,
        match="validation changed",
    ):
        with applied_preflight_compatibility(
            main_namespace=main,
            environment_namespace=environment,
            patch_plan=_plan(),
        ):
            main["validate_environment"] = alternate_validation

    assert main == original_main
    assert environment == original_environment


def test_compatibility_fails_if_environment_module_changes_during_context():
    main, environment = _namespaces()
    original_main = dict(main)
    original_environment = dict(environment)

    def alternate_pull():
        return None

    with pytest.raises(
        StrixPythonPreflightCompatibilityError,
        match="environment module changed",
    ):
        with applied_preflight_compatibility(
            main_namespace=main,
            environment_namespace=environment,
            patch_plan=_plan(),
        ):
            environment["pull_docker_image"] = alternate_pull

    assert main == original_main
    assert environment == original_environment
