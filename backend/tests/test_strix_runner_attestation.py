import hashlib
import json
from pathlib import Path

import pytest

from app.strix_runner_attestation import (
    STRIX_RELEASE_COMMIT,
    STRIX_RELEASE_VERSION,
    StrixRunnerAttestationError,
    attest_strix_runner,
)


ROOT = Path(__file__).resolve().parents[2]


def _write_fixture(tmp_path, *, version="strix 1.6.2"):
    binary = tmp_path / "strix"
    binary.write_bytes(b"fixture-strix-binary")
    binary.chmod(0o755)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "strix-runner-attestation-v1",
                "version": STRIX_RELEASE_VERSION,
                "source_commit": STRIX_RELEASE_COMMIT,
                "asset_name": "strix-1.6.2-linux-x86_64.tar.gz",
                "archive_sha256": (
                    "f3f29fa64bee420bf64f8911fb9f38e20270d406"
                    "f6df44cc2436252c2af0bc81"
                ),
                "binary_sha256": digest,
                "platform": "linux",
                "architecture": "amd64",
            }
        ),
        encoding="utf-8",
    )
    return binary, manifest, version


def test_runner_attestation_accepts_exact_pinned_release(tmp_path, monkeypatch):
    binary, manifest, version = _write_fixture(tmp_path)
    monkeypatch.setattr(
        "app.strix_runner_attestation._read_cli_version",
        lambda *_args, **_kwargs: version,
    )
    monkeypatch.setattr(
        "app.strix_runner_attestation._docker_socket_present",
        lambda: False,
    )

    result = attest_strix_runner(binary_path=binary, manifest_path=manifest)

    assert result["ready"] is True
    assert result["version"] == "1.6.2"
    assert result["source_commit"] == STRIX_RELEASE_COMMIT
    assert result["cli_version"] == "strix 1.6.2"
    assert result["archive_verified"] is True
    assert result["binary_verified"] is True
    assert result["docker_socket_present"] is False
    assert result["active_execution_enabled"] is False


def test_runner_attestation_rejects_binary_tampering(tmp_path, monkeypatch):
    binary, manifest, version = _write_fixture(tmp_path)
    binary.write_bytes(b"tampered")
    monkeypatch.setattr(
        "app.strix_runner_attestation._read_cli_version",
        lambda *_args, **_kwargs: version,
    )
    monkeypatch.setattr(
        "app.strix_runner_attestation._docker_socket_present",
        lambda: False,
    )

    with pytest.raises(StrixRunnerAttestationError, match="binary digest"):
        attest_strix_runner(binary_path=binary, manifest_path=manifest)


def test_runner_attestation_rejects_wrong_cli_version(tmp_path, monkeypatch):
    binary, manifest, _version = _write_fixture(tmp_path)
    monkeypatch.setattr(
        "app.strix_runner_attestation._read_cli_version",
        lambda *_args, **_kwargs: "strix 1.6.3",
    )
    monkeypatch.setattr(
        "app.strix_runner_attestation._docker_socket_present",
        lambda: False,
    )

    with pytest.raises(StrixRunnerAttestationError, match="CLI version"):
        attest_strix_runner(binary_path=binary, manifest_path=manifest)


def test_runner_attestation_rejects_docker_socket(tmp_path, monkeypatch):
    binary, manifest, version = _write_fixture(tmp_path)
    monkeypatch.setattr(
        "app.strix_runner_attestation._read_cli_version",
        lambda *_args, **_kwargs: version,
    )
    monkeypatch.setattr(
        "app.strix_runner_attestation._docker_socket_present",
        lambda: True,
    )

    with pytest.raises(StrixRunnerAttestationError, match="Docker socket"):
        attest_strix_runner(binary_path=binary, manifest_path=manifest)


def test_runner_dockerfile_pins_official_release_assets():
    dockerfile = (ROOT / "backend" / "Dockerfile.strix-runner").read_text()

    assert "STRIX_VERSION=1.6.2" in dockerfile
    assert (
        "f3f29fa64bee420bf64f8911fb9f38e20270d406f6df44cc2436252c2af0bc81"
        in dockerfile
    )
    assert (
        "4a4cba115bda8b89d7bbfabe960246a480ff43563144959b2e33477955aa6df2"
        in dockerfile
    )
    assert "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2" in dockerfile
    assert "sha256sum -c -" in dockerfile
    assert 'grep -Fx "strix ${STRIX_VERSION}"' in dockerfile
    assert "COPY app/strix_runner_attestation.py" in dockerfile
    assert "COPY app/__init__.py" not in dockerfile


def test_runner_compose_service_is_internal_and_inert():
    compose = (ROOT / "docker-compose.yml").read_text()
    block = compose.split("  strix-runner:", 1)[1].split(
        "\n  scanner-worker:",
        1,
    )[0]

    assert 'profiles: ["strix-runner"]' in block
    assert "dockerfile: Dockerfile.strix-runner" in block
    assert "networks: [strix-broker]" in block
    assert "\n    ports:" not in block
    assert "\n    volumes:" not in block
    assert "docker.sock" not in block
    assert "read_only: true" in block
    assert "no-new-privileges:true" in block
    assert "cap_drop:" in block
    assert "- ALL" in block
    assert 'XBOW_STRIX_ACTIVE_EXECUTION: "false"' in block


def test_ci_builds_strix_runner_profile():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert (
        "docker compose --profile strix-runner build --pull strix-runner"
        in workflow
    )



def test_ci_executes_runner_runtime_smoke():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    script = (
        ROOT / "scripts" / "verify-strix-runner-runtime.sh"
    ).read_text()

    assert "bash -n scripts/verify-strix-runner-runtime.sh" in workflow
    assert "bash scripts/verify-strix-runner-runtime.sh" in workflow
    assert "app.strix_runner_attestation --check" in script
    assert "socket.create_connection" in script
    assert '("1.1.1.1", 443)' in script
    assert "direct public TCP egress unexpectedly available" in script
