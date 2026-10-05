from __future__ import annotations

import pytest

from app.strix_python_bootstrap_plan import (
    STRIX_PYTHON_BOOTSTRAP_PLAN_SCHEMA,
    StrixPythonBootstrapPlanError,
    build_bootstrap_plan,
)


def _compat() -> dict:
    return {
        "schema": "strix-python-compat-probe-v1",
        "strix_version": "1.6.2",
        "backend": "xbow-remote-v1",
        "hook_loaded_in_python_runtime": True,
        "supports_bind_mounts": False,
        "active_execution_enabled": False,
        "upstream_docker_preflight_required": True,
        "entrypoint_enabled": False,
        "upstream_main_blob_sha1": (
            "c9bd559614a4b6a952229500721216be6df50c62"
        ),
        "upstream_environment_blob_sha1": (
            "522067df84a046379341f0e243dea57c9205b6b1"
        ),
        "docker_preflight_symbols": [
            "check_docker_installed",
            "pull_docker_image",
        ],
        "preserved_validation_symbol": "validate_environment",
        "preflight_call_order_verified": True,
    }


def _lock() -> dict:
    return {
        "schema": "strix-python-lock-probe-v1",
        "source_commit": "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2",
        "strix_version": "1.6.2",
        "python_requirement": ">=3.12",
        "uv_lock_version": 1,
        "uv_lock_revision": 3,
        "pyproject_blob_sha1": "b78fb3aa90936edaedc86cf634d34de89bcb9f5b",
        "uv_lock_blob_sha1": "2cb4cb5f0c4732dce1dc3cca21406ae63f66b148",
        "direct_dependency_count": 15,
        "dependency_lock_attested": True,
        "runtime_install_enabled": False,
    }


def _toolchain() -> dict:
    return {
        "schema": "strix-python-runtime-lock-v1",
        "source_commit": "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2",
        "strix_version": "1.6.2",
        "python_version": "3.12.14",
        "uv_version": "0.12.10",
        "architecture": "amd64",
        "uv_asset": "uv-x86_64-unknown-linux-gnu.tar.gz",
        "uv_sha256": "a" * 64,
        "toolchain_attested": True,
        "runtime_install_enabled": False,
        "active_execution_enabled": False,
    }


def test_bootstrap_plan_composes_all_attestations():
    result = build_bootstrap_plan(
        compatibility=_compat(),
        dependency_lock=_lock(),
        toolchain=_toolchain(),
    )

    assert result == {
        "schema": STRIX_PYTHON_BOOTSTRAP_PLAN_SCHEMA,
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


@pytest.mark.parametrize(
    ("descriptor_name", "mutate"),
    (
        (
            "compatibility",
            lambda value: value.update(strix_version="1.6.3"),
        ),
        (
            "compatibility",
            lambda value: value.update(active_execution_enabled=True),
        ),
        (
            "compatibility",
            lambda value: value.update(
                docker_preflight_symbols=["check_docker_installed"],
            ),
        ),
        (
            "dependency_lock",
            lambda value: value.update(runtime_install_enabled=True),
        ),
        (
            "dependency_lock",
            lambda value: value.update(dependency_lock_attested=False),
        ),
        (
            "toolchain",
            lambda value: value.update(active_execution_enabled=True),
        ),
        (
            "toolchain",
            lambda value: value.update(source_commit="0" * 40),
        ),
    ),
)
def test_bootstrap_plan_fails_closed_on_attestation_mismatch(
    descriptor_name,
    mutate,
):
    descriptors = {
        "compatibility": _compat(),
        "dependency_lock": _lock(),
        "toolchain": _toolchain(),
    }
    mutate(descriptors[descriptor_name])

    with pytest.raises(StrixPythonBootstrapPlanError):
        build_bootstrap_plan(**descriptors)


def test_bootstrap_plan_rejects_unknown_fields():
    compatibility = _compat()
    compatibility["unexpected"] = True

    with pytest.raises(StrixPythonBootstrapPlanError, match="contract"):
        build_bootstrap_plan(
            compatibility=compatibility,
            dependency_lock=_lock(),
            toolchain=_toolchain(),
        )
