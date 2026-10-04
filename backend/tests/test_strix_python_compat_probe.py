from pathlib import Path

import pytest

from app.strix_python_compat_probe import (
    StrixPythonCompatError,
    probe_python_runtime,
)


def test_python_runtime_probe_reports_hook_and_docker_preflight(monkeypatch, tmp_path):
    source = tmp_path / "main.py"
    source.write_text(
        "from strix.interface.environment import (\n"
        "    check_docker_installed,\n"
        "    pull_docker_image,\n"
        "    validate_environment,\n"
        ")\n"
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
    environment_source = tmp_path / "environment.py"
    environment_source.write_text("fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.strix_python_compat_probe._upstream_source_path",
        lambda relative: (
            source
            if relative == "strix/interface/main.py"
            else environment_source
        ),
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._git_blob_sha1",
        lambda path: (
            "c9bd559614a4b6a952229500721216be6df50c62"
            if path == source
            else "522067df84a046379341f0e243dea57c9205b6b1"
        ),
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
    environment_source = tmp_path / "environment.py"
    environment_source.write_text("fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.strix_python_compat_probe._upstream_source_path",
        lambda relative: (
            source
            if relative == "strix/interface/main.py"
            else environment_source
        ),
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._git_blob_sha1",
        lambda path: (
            "c9bd559614a4b6a952229500721216be6df50c62"
            if path == source
            else "522067df84a046379341f0e243dea57c9205b6b1"
        ),
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
    environment_source = tmp_path / "environment.py"
    environment_source.write_text("fixture\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.strix_python_compat_probe._upstream_source_path",
        lambda relative: (
            source
            if relative == "strix/interface/main.py"
            else environment_source
        ),
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


def test_git_blob_sha1_matches_git_object_identity(tmp_path):
    from app.strix_python_compat_probe import _git_blob_sha1

    source = tmp_path / "fixture.txt"
    source.write_bytes(b"hello\n")

    assert _git_blob_sha1(source) == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_python_runtime_probe_requires_exact_upstream_blob_ids(
    monkeypatch,
    tmp_path,
):
    main_source = tmp_path / "main.py"
    main_source.write_text(
        "from strix.interface.environment import (\n"
        "    check_docker_installed,\n"
        "    pull_docker_image,\n"
        "    validate_environment,\n"
        ")\n"
        "def main():\n"
        "    check_docker_installed()\n"
        "    pull_docker_image()\n"
        "    validate_environment()\n",
        encoding="utf-8",
    )
    environment_source = tmp_path / "environment.py"
    environment_source.write_text("fixture\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.strix_python_compat_probe._installed_strix_version",
        lambda: "1.6.2",
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._upstream_source_path",
        lambda relative: (
            main_source
            if relative == "strix/interface/main.py"
            else environment_source
        ),
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._git_blob_sha1",
        lambda path: (
            "c9bd559614a4b6a952229500721216be6df50c62"
            if path == main_source
            else "522067df84a046379341f0e243dea57c9205b6b1"
        ),
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

    assert result["upstream_main_blob_sha1"] == (
        "c9bd559614a4b6a952229500721216be6df50c62"
    )
    assert result["upstream_environment_blob_sha1"] == (
        "522067df84a046379341f0e243dea57c9205b6b1"
    )


def test_python_runtime_probe_rejects_upstream_blob_mismatch(
    monkeypatch,
    tmp_path,
):
    main_source = tmp_path / "main.py"
    main_source.write_text(
        "check_docker_installed()\n"
        "pull_docker_image()\n"
        "validate_environment()\n",
        encoding="utf-8",
    )
    environment_source = tmp_path / "environment.py"
    environment_source.write_text("fixture\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.strix_python_compat_probe._installed_strix_version",
        lambda: "1.6.2",
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._upstream_source_path",
        lambda relative: (
            main_source
            if relative == "strix/interface/main.py"
            else environment_source
        ),
    )
    monkeypatch.setattr(
        "app.strix_python_compat_probe._git_blob_sha1",
        lambda _path: "0" * 40,
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

    with pytest.raises(StrixPythonCompatError, match="source identity"):
        probe_python_runtime()


def test_preflight_structure_identifies_only_docker_checks_to_patch():
    from app.strix_python_compat_probe import _verify_preflight_structure

    descriptor = _verify_preflight_structure(
        "from strix.interface.environment import (\n"
        "    check_docker_installed,\n"
        "    pull_docker_image,\n"
        "    validate_environment,\n"
        ")\n"
        "def main():\n"
        "    check_docker_installed()\n"
        "    pull_docker_image()\n"
        "    validate_environment()\n"
    )

    assert descriptor == {
        "docker_preflight_symbols": [
            "check_docker_installed",
            "pull_docker_image",
        ],
        "preserved_validation_symbol": "validate_environment",
        "preflight_call_order_verified": True,
    }


@pytest.mark.parametrize(
    "source",
    (
        (
            "from strix.interface.environment import "
            "check_docker_installed, pull_docker_image\n"
            "def main():\n"
            "    check_docker_installed()\n"
            "    pull_docker_image()\n"
        ),
        (
            "from strix.interface.environment import (\n"
            "    check_docker_installed,\n"
            "    pull_docker_image,\n"
            "    validate_environment,\n"
            ")\n"
            "def main():\n"
            "    pull_docker_image()\n"
            "    check_docker_installed()\n"
            "    validate_environment()\n"
        ),
    ),
)
def test_preflight_structure_rejects_changed_scope_or_order(source):
    from app.strix_python_compat_probe import _verify_preflight_structure

    with pytest.raises(StrixPythonCompatError, match="preflight structure"):
        _verify_preflight_structure(source)
