from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
from typing import Any

from .strix_python_preflight_patch_plan import (
    STRIX_PYTHON_PREFLIGHT_PATCH_PLAN_SCHEMA,
)


STRIX_PYTHON_PREFLIGHT_COMPATIBILITY_SCHEMA = (
    "strix-python-preflight-compatibility-v1"
)
_PATCH_SYMBOLS = (
    "check_docker_installed",
    "pull_docker_image",
)
_PRESERVED_SYMBOL = "validate_environment"
_PLAN_KEYS = {
    "schema",
    "target_module",
    "replacement_symbols",
    "preserved_symbols",
    "replacement_behavior",
    "mutation_performed",
    "patch_application_enabled",
    "entrypoint_called",
    "active_execution_enabled",
}


class StrixPythonPreflightCompatibilityError(RuntimeError):
    pass


def _verified_noop_preflight(*_args: Any, **_kwargs: Any) -> None:
    return None


def _verify_patch_plan(plan: Mapping[str, Any]) -> None:
    if set(plan) != _PLAN_KEYS:
        raise StrixPythonPreflightCompatibilityError(
            "preflight patch plan contract changed"
        )
    if (
        plan.get("schema") != STRIX_PYTHON_PREFLIGHT_PATCH_PLAN_SCHEMA
        or plan.get("target_module") != "strix.interface.main"
        or plan.get("replacement_symbols") != list(_PATCH_SYMBOLS)
        or plan.get("preserved_symbols") != [_PRESERVED_SYMBOL]
        or plan.get("replacement_behavior") != "verified_noop_preflight_only"
        or plan.get("mutation_performed") is not False
        or plan.get("patch_application_enabled") is not False
        or plan.get("entrypoint_called") is not False
        or plan.get("active_execution_enabled") is not False
    ):
        raise StrixPythonPreflightCompatibilityError(
            "preflight patch plan is not safely inert"
        )


def _verify_pre_patch_namespaces(
    *,
    main_namespace: Mapping[str, Any],
    environment_namespace: Mapping[str, Any],
) -> dict[str, Any]:
    originals: dict[str, Any] = {}
    for symbol in (*_PATCH_SYMBOLS, _PRESERVED_SYMBOL):
        main_value = main_namespace.get(symbol)
        environment_value = environment_namespace.get(symbol)
        if (
            not callable(main_value)
            or not callable(environment_value)
            or main_value is not environment_value
        ):
            raise StrixPythonPreflightCompatibilityError(
                f"preflight symbol identity mismatch: {symbol}"
            )
        originals[symbol] = main_value
    return originals


@contextmanager
def applied_preflight_compatibility(
    *,
    main_namespace: MutableMapping[str, Any],
    environment_namespace: MutableMapping[str, Any],
    patch_plan: Mapping[str, Any],
) -> Iterator[dict[str, Any]]:
    """Temporarily bypass only the attested Docker preflight aliases in main.

    The upstream environment module and validate_environment are not changed by
    the compatibility layer. No Strix entrypoint is called here.
    """

    _verify_patch_plan(patch_plan)
    originals = _verify_pre_patch_namespaces(
        main_namespace=main_namespace,
        environment_namespace=environment_namespace,
    )
    body_error: BaseException | None = None
    patched_symbols: list[str] = []

    try:
        for symbol in _PATCH_SYMBOLS:
            main_namespace[symbol] = _verified_noop_preflight
            patched_symbols.append(symbol)

        if any(
            main_namespace.get(symbol) is not _verified_noop_preflight
            for symbol in _PATCH_SYMBOLS
        ):
            raise StrixPythonPreflightCompatibilityError(
                "preflight compatibility patch did not apply exactly"
            )
        if (
            main_namespace.get(_PRESERVED_SYMBOL)
            is not originals[_PRESERVED_SYMBOL]
            or environment_namespace.get(_PRESERVED_SYMBOL)
            is not originals[_PRESERVED_SYMBOL]
        ):
            raise StrixPythonPreflightCompatibilityError(
                "environment validation was modified"
            )
        if any(
            environment_namespace.get(symbol) is not originals[symbol]
            for symbol in _PATCH_SYMBOLS
        ):
            raise StrixPythonPreflightCompatibilityError(
                "environment module was unexpectedly modified"
            )

        yield {
            "schema": STRIX_PYTHON_PREFLIGHT_COMPATIBILITY_SCHEMA,
            "target_module": "strix.interface.main",
            "replacement_symbols": list(_PATCH_SYMBOLS),
            "replacement_behavior": "verified_noop_preflight_only",
            "mutation_performed": True,
            "patch_application_enabled": True,
            "compatibility_applied": True,
            "environment_module_mutated": False,
            "environment_validation_preserved": True,
            "entrypoint_called": False,
            "active_execution_enabled": False,
        }
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        validation_changed = (
            main_namespace.get(_PRESERVED_SYMBOL)
            is not originals[_PRESERVED_SYMBOL]
            or environment_namespace.get(_PRESERVED_SYMBOL)
            is not originals[_PRESERVED_SYMBOL]
        )
        environment_changed = any(
            environment_namespace.get(symbol) is not originals[symbol]
            for symbol in _PATCH_SYMBOLS
        )
        for symbol in reversed(patched_symbols):
            main_namespace[symbol] = originals[symbol]
        main_namespace[_PRESERVED_SYMBOL] = originals[_PRESERVED_SYMBOL]
        for symbol in _PATCH_SYMBOLS:
            environment_namespace[symbol] = originals[symbol]
        environment_namespace[_PRESERVED_SYMBOL] = originals[_PRESERVED_SYMBOL]

        if body_error is None and validation_changed:
            raise StrixPythonPreflightCompatibilityError(
                "environment validation changed while compatibility was applied"
            )
        if body_error is None and environment_changed:
            raise StrixPythonPreflightCompatibilityError(
                "environment module changed while compatibility was applied"
            )
