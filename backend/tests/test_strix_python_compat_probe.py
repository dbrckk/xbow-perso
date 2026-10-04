from pathlib import Path

import pytest

from app.strix_python_compat_probe import (
    StrixPythonCompatError,
    probe_python_runtime,
)


def test_python_runtime_probe_reports_hook_and_docker_preflight(monkeypatch, tmp_path):
    source = tmp_path / "main.py"
    source.write_text(
        "def main():\n"
        "    check_docker_installed()\n"
        "    pull_docker_image()\n"
        "    validate_environment()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._installed_strix_version",
        lambda: "1.6.2",
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._upstream_main_path",
        lambda: source,
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe.register_xbow_backend",
        lambda: {
            "backend": "xbow-remote-v1",
            "registered": True,
            "supports_bind_mounts": False,
            "active_execution_enabled": False,
        },
    )

    result = probe_python_runtime()

    assert result == {
        "schema": "strix-python-compat-probe-v1",
        "strix_version": "1.6.2",
        "backend": "xbow-remote-v1",
        "hook_loaded_in_python_runtime": True,
        "supports_bind_mounts": False,
        "active_execution_enabled": False,
        "upstream_docker_preflight_required": True,
        "entrypoint_enabled": False,
    }


def test_python_runtime_probe_rejects_wrong_version(monkeypatch):
    monkeypatch.setattr(
        "app.strix_python_compat_probe._installed_strix_version",
        lambda: "1.6.3",
    )

    with pytest.raises(StrixPythonCompatError, match="version"):
        probe_python_runtime()


def test_python_runtime_probe_fails_if_preflight_markers_change(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "main.py"
    source.write_text("def main():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.strix_python_compat_probe._installed_strix_version",
        lambda: "1.6.2",
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._upstream_main_path",
        lambda: source,
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe.register_xbow_backend",
        lambda: {
            "backend": "xbow-remote-v1",
            "registered": True,
            "supports_bind_mounts": False,
            "active_execution_enabled": False,
        },
    )

    with pytest.raises(StrixPythonCompatError, match="preflight"):
        probe_python_runtime()


def test_probe_source_read_is_bounded(monkeypatch, tmp_path):
    source = tmp_path / "main.py"
    source.write_bytes(b"x" * (512 * 1024 + 1))
    monkeypatch.setattr(
        "app.strix_python_compat_probe._installed_strix_version",
        lambda: "1.6.2",
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._upstream_main_path",
        lambda: source,
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe.register_xbow_backend",
        lambda: {
            "backend": "xbow-remote-v1",
            "registered": True,
            "supports_bind_mounts": False,
            "active_execution_enabled": False,
        },
    )

    with pytest.raises(StrixPythonCompatError, match="source size"):
        probe_python_runtime()


def test_ci_runs_python_compat_probe_against_pinned_wheel():
    workflow = Path(".github/workflows/ci.yml").read_text()

    assert "app.strix_python_compat_probe --self-test" in workflow
