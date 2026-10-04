import asyncio
import os
import sys
import types
from pathlib import Path

import pytest

from app import strix_backend_hook
from app.strix_backend_hook import (
    STRIX_BACKEND_NAME,
    StrixBackendBlocked,
    StrixBackendHookError,
    register_xbow_backend,
    self_test,
)


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _restore_runtime_backend_env(monkeypatch):
    monkeypatch.delenv("STRIX_RUNTIME_BACKEND", raising=False)


def _install_fake_strix_backend_api(monkeypatch, *, existing=None):
    registry = {"docker": object()}
    bind_mount_backends = {"docker"}
    if existing is not None:
        registry[STRIX_BACKEND_NAME] = existing

    backend_module = types.ModuleType("strix.runtime.backends")

    def register_backend(name, backend, *, supports_bind_mounts=False):
        registry[name] = backend
        if supports_bind_mounts:
            bind_mount_backends.add(name)
        else:
            bind_mount_backends.discard(name)

    def get_backend(name):
        return registry[name]

    def supported_backends():
        return sorted(registry)

    def backend_supports_bind_mounts(name):
        return name in bind_mount_backends

    backend_module.register_backend = register_backend
    backend_module.get_backend = get_backend
    backend_module.supported_backends = supported_backends
    backend_module.backend_supports_bind_mounts = (
        backend_supports_bind_mounts
    )

    strix_module = types.ModuleType("strix")
    strix_module.__path__ = []
    runtime_module = types.ModuleType("strix.runtime")
    runtime_module.__path__ = []

    monkeypatch.setitem(sys.modules, "strix", strix_module)
    monkeypatch.setitem(sys.modules, "strix.runtime", runtime_module)
    monkeypatch.setitem(
        sys.modules,
        "strix.runtime.backends",
        backend_module,
    )
    return registry


def test_registers_fail_closed_backend_without_bind_mounts(monkeypatch):
    registry = _install_fake_strix_backend_api(monkeypatch)
    monkeypatch.delenv("STRIX_RUNTIME_BACKEND", raising=False)

    result = register_xbow_backend()

    assert result == {
        "backend": "xbow-remote-v1",
        "registered": True,
        "supports_bind_mounts": False,
        "active_execution_enabled": False,
    }
    assert os.environ["STRIX_RUNTIME_BACKEND"] == STRIX_BACKEND_NAME
    assert registry[STRIX_BACKEND_NAME] is strix_backend_hook._blocked_backend


def test_registration_is_idempotent_for_same_backend(monkeypatch):
    _install_fake_strix_backend_api(monkeypatch)

    first = register_xbow_backend()
    second = register_xbow_backend()

    assert first == second


def test_backend_name_collision_fails_closed(monkeypatch):
    _install_fake_strix_backend_api(
        monkeypatch,
        existing=lambda **_kwargs: None,
    )

    with pytest.raises(StrixBackendHookError, match="name collision"):
        register_xbow_backend()


def test_registered_backend_always_blocks_execution(monkeypatch):
    registry = _install_fake_strix_backend_api(monkeypatch)
    register_xbow_backend()
    backend = registry[STRIX_BACKEND_NAME]

    with pytest.raises(StrixBackendBlocked, match="not wired"):
        asyncio.run(
            backend(
                image="unused",
                manifest=object(),
                exposed_ports=(),
                bind_mounts=[],
            )
        )


def test_self_test_requires_exact_strix_version(monkeypatch):
    _install_fake_strix_backend_api(monkeypatch)
    monkeypatch.setattr(
        strix_backend_hook,
        "_installed_strix_version",
        lambda: "1.6.3",
    )

    with pytest.raises(StrixBackendHookError, match="unexpected Strix version"):
        self_test()


def test_self_test_proves_fail_closed_backend(monkeypatch):
    _install_fake_strix_backend_api(monkeypatch)
    monkeypatch.setattr(
        strix_backend_hook,
        "_installed_strix_version",
        lambda: "1.6.2",
    )

    result = self_test()

    assert result["schema"] == "strix-backend-hook-v1"
    assert result["strix_version"] == "1.6.2"
    assert result["backend"] == STRIX_BACKEND_NAME
    assert result["fail_closed_verified"] is True
    assert result["active_execution_enabled"] is False


def test_ci_checks_real_pinned_strix_backend_api():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "Verify pinned Strix backend hook" in workflow
    assert (
        "strix_agent-1.6.2-py3-none-manylinux_2_17_x86_64.whl"
        in workflow
    )
    assert (
        "1a93fbf0f18fad6bf4802c41fa5e032ce50880a655fddee47f6bec4f1ea2155b"
        in workflow
    )
    assert "pip install --no-deps --target" in workflow
    assert "python -m app.strix_backend_hook --self-test" in workflow
