from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from .strix_backend_hook import (
    STRIX_BACKEND_NAME,
    register_xbow_backend,
)
from .strix_python_preflight_compatibility import (
    applied_preflight_compatibility,
)
from .strix_python_preflight_patch_plan import build_preflight_patch_plan
from .strix_python_preflight_surface import inspect_preflight_surface


STRIX_PYTHON_BOOTSTRAP_RUNTIME_SCHEMA = "strix-python-bootstrap-runtime-v1"
_ENVIRONMENT_MODULE = "strix.interface.environment"
_MAIN_MODULE = "strix.interface.main"
_EXPECTED_BACKEND_DESCRIPTOR = {
    "backend": STRIX_BACKEND_NAME,
    "registered": True,
    "supports_bind_mounts": False,
    "active_execution_enabled": False,
}


class StrixPythonBootstrapRuntimeError(RuntimeError):
    pass


def _module_namespace(module: Any, name: str) -> MutableMapping[str, Any]:
    try:
        namespace = vars(module)
    except TypeError as exc:
        raise StrixPythonBootstrapRuntimeError(
            f"{name} module namespace is unavailable"
        ) from exc
    if not isinstance(namespace, MutableMapping):
        raise StrixPythonBootstrapRuntimeError(
            f"{name} module namespace is not mutable"
        )
    return namespace


def _verify_backend_descriptor(descriptor: Mapping[str, Any]) -> None:
    if dict(descriptor) != _EXPECTED_BACKEND_DESCRIPTOR:
        raise StrixPythonBootstrapRuntimeError(
            "Strix backend registration descriptor is unexpected"
        )


@contextmanager
def prepared_strix_python_runtime(
    *,
    bootstrap_plan: dict[str, Any],
    import_module: Callable[[str], Any],
    module_cache: Mapping[str, Any] | None = None,
) -> Iterator[tuple[dict[str, Any], Any]]:
    """Prepare the pinned Strix Python runtime without invoking its entrypoint.

    The custom backend is registered before strix.interface.main is imported.
    Only the two attested Docker-preflight aliases are then patched, and the
    upstream environment validation callable remains untouched.
    """

    cache = sys.modules if module_cache is None else module_cache
    if _MAIN_MODULE in cache:
        raise StrixPythonBootstrapRuntimeError(
            "Strix main module was imported before backend bootstrap"
        )

    before_import = register_xbow_backend()
    _verify_backend_descriptor(before_import)
    if os.environ.get("STRIX_RUNTIME_BACKEND") != STRIX_BACKEND_NAME:
        raise StrixPythonBootstrapRuntimeError(
            "Strix runtime backend selection was not pinned"
        )

    environment_module = import_module(_ENVIRONMENT_MODULE)
    main_module = import_module(_MAIN_MODULE)

    after_import = register_xbow_backend()
    _verify_backend_descriptor(after_import)
    if after_import != before_import:
        raise StrixPythonBootstrapRuntimeError(
            "Strix backend registry changed during interface import"
        )

    environment_namespace = _module_namespace(
        environment_module,
        _ENVIRONMENT_MODULE,
    )
    main_namespace = _module_namespace(main_module, _MAIN_MODULE)

    surface = inspect_preflight_surface(
        main_namespace=main_namespace,
        environment_namespace=environment_namespace,
        bootstrap_plan=bootstrap_plan,
    )
    patch_plan = build_preflight_patch_plan(surface)

    with applied_preflight_compatibility(
        main_namespace=main_namespace,
        environment_namespace=environment_namespace,
        patch_plan=patch_plan,
    ) as compatibility:
        if os.environ.get("STRIX_RUNTIME_BACKEND") != STRIX_BACKEND_NAME:
            raise StrixPythonBootstrapRuntimeError(
                "Strix runtime backend selection changed during bootstrap"
            )
        yield (
            {
                "schema": STRIX_PYTHON_BOOTSTRAP_RUNTIME_SCHEMA,
                "backend": STRIX_BACKEND_NAME,
                "backend_registered_before_main_import": True,
                "backend_registry_stable_after_import": True,
                "environment_module": _ENVIRONMENT_MODULE,
                "main_module": _MAIN_MODULE,
                "preflight_surface_attested": True,
                "preflight_patch_plan_attested": True,
                "compatibility_applied": (
                    compatibility.get("compatibility_applied") is True
                ),
                "environment_validation_preserved": (
                    compatibility.get("environment_validation_preserved")
                    is True
                ),
                "entrypoint_called": False,
                "active_execution_enabled": False,
            },
            main_module,
        )


def _self_test_plan() -> dict[str, Any]:
    return {
        "schema": "strix-python-bootstrap-plan-v1",
        "strix_version": "1.6.2",
        "source_commit": "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2",
        "backend": STRIX_BACKEND_NAME,
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


def self_test() -> dict[str, Any]:
    def check_docker_installed() -> None:
        raise AssertionError("Docker preflight alias was not patched")

    def pull_docker_image() -> None:
        raise AssertionError("Docker image preflight alias was not patched")

    def validate_environment() -> str:
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
    imports: list[str] = []

    def synthetic_import(name: str) -> Any:
        imports.append(name)
        if name == _ENVIRONMENT_MODULE:
            return environment
        if name == _MAIN_MODULE:
            return main
        raise StrixPythonBootstrapRuntimeError(
            f"unexpected self-test import: {name}"
        )

    with prepared_strix_python_runtime(
        bootstrap_plan=_self_test_plan(),
        import_module=synthetic_import,
        module_cache={},
    ) as (descriptor, prepared_main):
        if prepared_main.check_docker_installed() is not None:
            raise StrixPythonBootstrapRuntimeError(
                "Docker preflight compatibility did not return no-op"
            )
        if prepared_main.pull_docker_image() is not None:
            raise StrixPythonBootstrapRuntimeError(
                "Docker image compatibility did not return no-op"
            )
        if prepared_main.validate_environment is not validate_environment:
            raise StrixPythonBootstrapRuntimeError(
                "environment validation identity changed"
            )
        result = {
            **descriptor,
            "synthetic_interface_imports": True,
            "import_order": list(imports),
            "bootstrap_contract_verified": True,
        }

    if main.check_docker_installed is not check_docker_installed:
        raise StrixPythonBootstrapRuntimeError(
            "Docker preflight alias was not restored"
        )
    if main.pull_docker_image is not pull_docker_image:
        raise StrixPythonBootstrapRuntimeError(
            "Docker image preflight alias was not restored"
        )
    if main.validate_environment is not validate_environment:
        raise StrixPythonBootstrapRuntimeError(
            "environment validation was not restored"
        )
    return result


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        raise StrixPythonBootstrapRuntimeError(
            "only --self-test is supported until entrypoint execution is admitted"
        )
    print(
        json.dumps(
            self_test(),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
