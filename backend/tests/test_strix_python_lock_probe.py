from pathlib import Path

import pytest

from app.strix_python_lock_probe import (
    StrixPythonLockError,
    probe_dependency_lock,
)


EXPECTED_DEPENDENCIES = [
    "caido-sdk-client",
    "cryptography",
    "cvss",
    "docker",
    "litellm",
    "markdown-it-py",
    "openai",
    "openai-agents",
    "pydantic",
    "pydantic-settings",
    "pypdf",
    "pyyaml",
    "reportlab",
    "requests",
    "rich",
]


def _write_fixture(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "strix-agent"\n'
        'version = "1.6.2"\n'
        'requires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    lock = tmp_path / "uv.lock"
    dependency_rows = "\n".join(
        f'    {{ name = "{name}" }},'
        for name in EXPECTED_DEPENDENCIES
    )
    lock.write_text(
        "version = 1\n"
        "revision = 3\n"
        'requires-python = ">=3.12"\n\n'
        "[[package]]\n"
        'name = "strix-agent"\n'
        'version = "1.6.2"\n'
        'source = { editable = "." }\n'
        "dependencies = [\n"
        f"{dependency_rows}\n"
        "]\n",
        encoding="utf-8",
    )
    return pyproject, lock


def test_dependency_lock_probe_accepts_exact_pinned_contract(
    monkeypatch,
    tmp_path,
):
    pyproject, lock = _write_fixture(tmp_path)
    monkeypatch.setattr(
        "app.strix_python_lock_probe._git_blob_sha1",
        lambda path: (
            "b78fb3aa90936edaedc86cf634d34de89bcb9f5b"
            if path == pyproject
            else "2cb4cb5f0c4732dce1dc3cca21406ae63f66b148"
        ),
    )

    result = probe_dependency_lock(
        pyproject_path=pyproject,
        lock_path=lock,
    )

    assert result == {
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


def test_dependency_lock_probe_rejects_blob_mismatch(monkeypatch, tmp_path):
    pyproject, lock = _write_fixture(tmp_path)
    monkeypatch.setattr(
        "app.strix_python_lock_probe._git_blob_sha1",
        lambda _path: "0" * 40,
    )

    with pytest.raises(StrixPythonLockError, match="source identity"):
        probe_dependency_lock(
            pyproject_path=pyproject,
            lock_path=lock,
        )


def test_dependency_lock_probe_rejects_changed_direct_dependencies(
    monkeypatch,
    tmp_path,
):
    pyproject, lock = _write_fixture(tmp_path)
    lock.write_text(
        lock.read_text(encoding="utf-8").replace(
            '    { name = "rich" },\n',
            "",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.strix_python_lock_probe._git_blob_sha1",
        lambda path: (
            "b78fb3aa90936edaedc86cf634d34de89bcb9f5b"
            if path == pyproject
            else "2cb4cb5f0c4732dce1dc3cca21406ae63f66b148"
        ),
    )

    with pytest.raises(StrixPythonLockError, match="dependencies"):
        probe_dependency_lock(
            pyproject_path=pyproject,
            lock_path=lock,
        )


def test_ci_attests_pinned_strix_dependency_lock():
    workflow = Path(".github/workflows/ci.yml").read_text()

    assert "python -m app.strix_python_lock_probe" in workflow
    assert "--self-test" in workflow
    assert "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2" in workflow
    assert "pyproject.toml" in workflow
    assert "uv.lock" in workflow
