from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from app.strix_python_bootstrap_runtime import (
    STRIX_PYTHON_BOOTSTRAP_RUNTIME_SCHEMA,
    StrixPythonBootstrapRuntimeError,
    prepared_strix_python_runtime,
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


def _modules():
    def check_docker_installed():
        return "docker"

    def pull_docker_image():
        return "image"

    def validate_environment():
        return "validated"

    environment = SimpleNamespace(
        check_docker_installed=check_docker_installed,
        pull_docker_image=pull_docker_image,
        validate_environment=validate_environment,
    )
    main = SimpleNamespace(
        check_docker_installed=check_docker_installed,
        pull_docker_image=pull_docker_image,
        validate_environment=validate_environment,
    )
    return main, environment


def _backend_descriptor() -> dict:
    return {
        "backend": "xbow-remote-v1",
        "registered": True,
        "supports_bind_mounts": False,
        "active_execution_enabled": False,
    }


def test_bootstrap_registers_backend_before_main_import_and_restores(monkeypatch):
    main, environment = _modules()
    originals = dict(vars(main))
    events = []

    def register():
        events.append("register_backend")
        os.environ["STRIX_RUNTIME_BACKEND"] = "xbow-remote-v1"
        return _backend_descriptor()

    def importer(name):
        events.append(f"import:{name}")
        if name == "strix.interface.environment":
            return environment
        if name == "strix.interface.main":
            return main
        raise AssertionError(name)

    monkeypatch.setattr(
        "app.strix_python_bootstrap_runtime.register_xbow_backend",
        register,
    )
    monkeypatch.delenv("STRIX_RUNTIME_BACKEND", raising=False)

    with prepared_strix_python_runtime(
        bootstrap_plan=_plan(),
        import_module=importer,
        module_cache={},
    ) as (descriptor, prepared_main):
        assert events == [
            "register_backend",
            "import:strix.interface.environment",
            "import:strix.interface.main",
            "register_backend",
        ]
        assert descriptor == {
            "schema": STRIX_PYTHON_BOOTSTRAP_RUNTIME_SCHEMA,
            "backend": "xbow-remote-v1",
            "backend_registered_before_main_import": True,
            "backend_registry_stable_after_import": True,
            "environment_module": "strix.interface.environment",
            "main_module": "strix.interface.main",
            "preflight_surface_attested": True,
            "preflight_patch_plan_attested": True,
            "compatibility_applied": True,
            "environment_validation_preserved": True,
            "entrypoint_called": False,
            "active_execution_enabled": False,
        }
        assert prepared_main.check_docker_installed() is None
        assert prepared_main.pull_docker_image() is None
        assert (
            prepared_main.validate_environment
            is environment.validate_environment
        )

    assert vars(main) == originals
    assert environment.check_docker_installed() == "docker"
    assert environment.pull_docker_image() == "image"
    assert environment.validate_environment() == "validated"


def test_bootstrap_rejects_preimported_main(monkeypatch):
    monkeypatch.setattr(
        "app.strix_python_bootstrap_runtime.register_xbow_backend",
        lambda: _backend_descriptor(),
    )

    with pytest.raises(
        StrixPythonBootstrapRuntimeError,
        match="imported before backend bootstrap",
    ):
        with prepared_strix_python_runtime(
            bootstrap_plan=_plan(),
            import_module=lambda _name: object(),
            module_cache={"strix.interface.main": object()},
        ):
            pass


def test_bootstrap_rejects_unexpected_backend_descriptor(monkeypatch):
    monkeypatch.setattr(
        "app.strix_python_bootstrap_runtime.register_xbow_backend",
        lambda: {
            **_backend_descriptor(),
            "active_execution_enabled": True,
        },
    )

    with pytest.raises(
        StrixPythonBootstrapRuntimeError,
        match="descriptor is unexpected",
    ):
        with prepared_strix_python_runtime(
            bootstrap_plan=_plan(),
            import_module=lambda _name: object(),
            module_cache={},
        ):
            pass


def test_bootstrap_rejects_backend_selection_drift(monkeypatch):
    calls = 0

    def register():
        nonlocal calls
        calls += 1
        os.environ["STRIX_RUNTIME_BACKEND"] = (
            "xbow-remote-v1" if calls == 1 else "unexpected"
        )
        return _backend_descriptor()

    main, environment = _modules()

    def importer(name):
        if name == "strix.interface.environment":
            return environment
        if name == "strix.interface.main":
            return main
        raise AssertionError(name)

    monkeypatch.setattr(
        "app.strix_python_bootstrap_runtime.register_xbow_backend",
        register,
    )

    with pytest.raises(
        StrixPythonBootstrapRuntimeError,
        match="selection changed during bootstrap",
    ):
        with prepared_strix_python_runtime(
            bootstrap_plan=_plan(),
            import_module=importer,
            module_cache={},
        ):
            pass


def test_bootstrap_fails_closed_on_tampered_plan(monkeypatch):
    main, environment = _modules()

    def register():
        os.environ["STRIX_RUNTIME_BACKEND"] = "xbow-remote-v1"
        return _backend_descriptor()

    monkeypatch.setattr(
        "app.strix_python_bootstrap_runtime.register_xbow_backend",
        register,
    )

    def importer(name):
        if name == "strix.interface.environment":
            return environment
        if name == "strix.interface.main":
            return main
        raise AssertionError(name)

    plan = _plan()
    plan["active_execution_enabled"] = True

    with pytest.raises(Exception):
        with prepared_strix_python_runtime(
            bootstrap_plan=plan,
            import_module=importer,
            module_cache={},
        ):
            pass
