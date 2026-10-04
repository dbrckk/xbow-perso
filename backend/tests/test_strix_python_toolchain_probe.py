import json
from pathlib import Path

import pytest

from app.strix_python_toolchain_probe import (
    StrixPythonToolchainError,
    probe_toolchain,
)


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_toolchain_manifest_is_inert_and_pinned():
    manifest = json.loads(
        (ROOT / "backend" / "strix-python-runtime.lock.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["schema"] == "strix-python-runtime-lock-v1"
    assert manifest["source_commit"] == (
        "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2"
    )
    assert manifest["strix_version"] == "1.6.2"
    assert manifest["release_build"]["python_version"] == "3.12.14"
    assert manifest["release_build"]["uv_version"] == "0.12.10"
    assert manifest["runtime_install_enabled"] is False
    assert manifest["active_execution_enabled"] is False


def test_toolchain_probe_accepts_exact_uv_archive(tmp_path, monkeypatch):
    archive = tmp_path / "uv.tar.gz"
    archive.write_bytes(b"fixture")
    manifest = ROOT / "backend" / "strix-python-runtime.lock.json"
    monkeypatch.setattr(
        "app.strix_python_toolchain_probe._sha256_file",
        lambda _path: (
            "173d95a0c32d18c896c46ba6fafbf3cf9c14ab74b033f81b76c883ef492a976b"
        ),
    )

    result = probe_toolchain(
        manifest_path=manifest,
        uv_archive_path=archive,
        architecture="amd64",
    )

    assert result["toolchain_attested"] is True
    assert result["python_version"] == "3.12.14"
    assert result["uv_version"] == "0.12.10"
    assert result["uv_asset"] == "uv-x86_64-unknown-linux-gnu.tar.gz"
    assert result["runtime_install_enabled"] is False
    assert result["active_execution_enabled"] is False


def test_toolchain_probe_rejects_digest_mismatch(tmp_path, monkeypatch):
    archive = tmp_path / "uv.tar.gz"
    archive.write_bytes(b"fixture")
    manifest = ROOT / "backend" / "strix-python-runtime.lock.json"
    monkeypatch.setattr(
        "app.strix_python_toolchain_probe._sha256_file",
        lambda _path: "0" * 64,
    )

    with pytest.raises(StrixPythonToolchainError, match="digest"):
        probe_toolchain(
            manifest_path=manifest,
            uv_archive_path=archive,
            architecture="amd64",
        )


def test_toolchain_probe_rejects_unknown_architecture(tmp_path):
    archive = tmp_path / "uv.tar.gz"
    archive.write_bytes(b"fixture")
    manifest = ROOT / "backend" / "strix-python-runtime.lock.json"

    with pytest.raises(StrixPythonToolchainError, match="unsupported"):
        probe_toolchain(
            manifest_path=manifest,
            uv_archive_path=archive,
            architecture="riscv64",
        )


def test_ci_verifies_official_uv_release_binary():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "uv-x86_64-unknown-linux-gnu.tar.gz" in workflow
    assert (
        "173d95a0c32d18c896c46ba6fafbf3cf9c14ab74b033f81b76c883ef492a976b"
        in workflow
    )
    assert "python -m app.strix_python_toolchain_probe" in workflow
    assert "uv 0.12.10" not in workflow
