import hashlib
import json
import stat
import subprocess

import pytest

from app.strix_runner import (
    PINNED_STRIX_ASSETS,
    PINNED_STRIX_UPSTREAM_COMMIT,
    PINNED_STRIX_VERSION,
    StrixRunnerAttestationError,
    attest_strix_runtime,
    health_document,
)


def _write_runtime(tmp_path, monkeypatch, *, architecture="amd64"):
    binary = tmp_path / "strix"
    binary.write_bytes(b"fixture-strix-binary")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)

    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    asset = PINNED_STRIX_ASSETS[architecture]["asset"]
    monkeypatch.setitem(
        PINNED_STRIX_ASSETS[architecture],
        "sha256",
        digest,
    )
    manifest = {
        "schema": "xbow-strix-runner-manifest-v1",
        "version": PINNED_STRIX_VERSION,
        "upstream_commit": PINNED_STRIX_UPSTREAM_COMMIT,
        "architecture": architecture,
        "asset": asset,
        "sha256": digest,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return binary, manifest_path, manifest


def test_runner_health_is_explicitly_attestation_only():
    result = health_document()

    assert result["status"] == "ok"
    assert result["mode"] == "attestation_only"
    assert result["execution_enabled"] is False
    assert result["network_access"] == "internal_only"
    assert result["docker_socket_allowed"] is False


def test_attestation_accepts_exact_binary_manifest_and_version(monkeypatch, tmp_path):
    binary, manifest_path, manifest = _write_runtime(tmp_path, monkeypatch)

    def run(args, **kwargs):
        assert args == [str(binary), "--version"]
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 5
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin"
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=f"strix {PINNED_STRIX_VERSION}\n",
            stderr="",
        )

    monkeypatch.setattr("app.strix_runner.subprocess.run", run)

    result = attest_strix_runtime(
        binary_path=binary,
        manifest_path=manifest_path,
    )

    assert result["status"] == "ready"
    assert result["mode"] == "attestation_only"
    assert result["execution_enabled"] is False
    assert result["version"] == PINNED_STRIX_VERSION
    assert result["sha256"] == manifest["sha256"]
    assert result["upstream_commit"] == PINNED_STRIX_UPSTREAM_COMMIT
    assert result["architecture"] == "amd64"
    assert result["asset"] == manifest["asset"]


def test_attestation_rejects_manifest_with_unexpected_version(monkeypatch, tmp_path):
    binary, manifest_path, manifest = _write_runtime(tmp_path, monkeypatch)
    manifest["version"] = "9.9.9"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(StrixRunnerAttestationError, match="version"):
        attest_strix_runtime(
            binary_path=binary,
            manifest_path=manifest_path,
        )


def test_attestation_rejects_manifest_with_unexpected_upstream_commit(
    monkeypatch,
    tmp_path,
):
    binary, manifest_path, manifest = _write_runtime(tmp_path, monkeypatch)
    manifest["upstream_commit"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(StrixRunnerAttestationError, match="upstream commit"):
        attest_strix_runtime(
            binary_path=binary,
            manifest_path=manifest_path,
        )


def test_attestation_rejects_manifest_asset_not_pinned_for_architecture(
    monkeypatch,
    tmp_path,
):
    binary, manifest_path, manifest = _write_runtime(tmp_path, monkeypatch)
    manifest["asset"] = "strix-1.6.2-linux-wrong.tar.gz"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(StrixRunnerAttestationError, match="asset"):
        attest_strix_runtime(
            binary_path=binary,
            manifest_path=manifest_path,
        )


def test_attestation_rejects_binary_hash_mismatch(monkeypatch, tmp_path):
    binary, manifest_path, manifest = _write_runtime(tmp_path, monkeypatch)
    manifest["sha256"] = "f" * 64
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(StrixRunnerAttestationError, match="sha256"):
        attest_strix_runtime(
            binary_path=binary,
            manifest_path=manifest_path,
        )


def test_attestation_rejects_symlink_binary(monkeypatch, tmp_path):
    binary, manifest_path, _manifest = _write_runtime(tmp_path, monkeypatch)
    symlink = tmp_path / "strix-link"
    symlink.symlink_to(binary)

    with pytest.raises(StrixRunnerAttestationError, match="symlink"):
        attest_strix_runtime(
            binary_path=symlink,
            manifest_path=manifest_path,
        )


def test_attestation_rejects_non_executable_binary(monkeypatch, tmp_path):
    binary, manifest_path, _manifest = _write_runtime(tmp_path, monkeypatch)
    binary.chmod(stat.S_IRUSR | stat.S_IWUSR)

    with pytest.raises(StrixRunnerAttestationError, match="executable"):
        attest_strix_runtime(
            binary_path=binary,
            manifest_path=manifest_path,
        )


def test_attestation_rejects_wrong_runtime_version(monkeypatch, tmp_path):
    binary, manifest_path, _manifest = _write_runtime(tmp_path, monkeypatch)

    monkeypatch.setattr(
        "app.strix_runner.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            stdout="strix 1.6.1\n",
            stderr="",
        ),
    )

    with pytest.raises(StrixRunnerAttestationError, match="runtime version"):
        attest_strix_runtime(
            binary_path=binary,
            manifest_path=manifest_path,
        )


def test_attestation_rejects_extra_manifest_fields(monkeypatch, tmp_path):
    binary, manifest_path, manifest = _write_runtime(tmp_path, monkeypatch)
    manifest["unexpected"] = "value"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(StrixRunnerAttestationError, match="manifest fields"):
        attest_strix_runtime(
            binary_path=binary,
            manifest_path=manifest_path,
        )


@pytest.mark.parametrize("architecture", ["amd64", "arm64"])
def test_pinned_release_assets_have_exact_sha256(architecture):
    item = PINNED_STRIX_ASSETS[architecture]

    assert item["asset"].startswith("strix-1.6.2-linux-")
    assert len(item["sha256"]) == 64
    int(item["sha256"], 16)
