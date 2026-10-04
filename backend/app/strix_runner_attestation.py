from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


STRIX_RELEASE_VERSION = "1.6.2"
STRIX_RELEASE_COMMIT = "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2"
STRIX_ATTESTATION_SCHEMA = "strix-runner-attestation-v1"

_RELEASES = {
    "amd64": {
        "asset_name": "strix-1.6.2-linux-x86_64.tar.gz",
        "archive_sha256": (
            "f3f29fa64bee420bf64f8911fb9f38e20270d406"
            "f6df44cc2436252c2af0bc81"
        ),
    },
    "arm64": {
        "asset_name": "strix-1.6.2-linux-arm64.tar.gz",
        "archive_sha256": (
            "4a4cba115bda8b89d7bbfabe960246a480ff4356"
            "3144959b2e33477955aa6df2"
        ),
    },
}


class StrixRunnerAttestationError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(path: Path) -> dict:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise StrixRunnerAttestationError(
            "Strix runner manifest is unavailable"
        ) from exc
    if len(payload) > 16 * 1024:
        raise StrixRunnerAttestationError(
            "Strix runner manifest exceeds size limit"
        )
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StrixRunnerAttestationError(
            "Strix runner manifest is invalid"
        ) from exc
    if not isinstance(data, dict):
        raise StrixRunnerAttestationError(
            "Strix runner manifest is invalid"
        )
    return data


def _read_cli_version(binary_path: Path) -> str:
    try:
        result = subprocess.run(
            [str(binary_path), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env={
                "PATH": os.environ.get("PATH", ""),
                "HOME": "/tmp",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StrixRunnerAttestationError(
            "Strix runner CLI version check failed"
        ) from exc
    return result.stdout.strip()


def _docker_socket_present() -> bool:
    return Path("/var/run/docker.sock").exists()


def _validate_manifest(data: dict) -> dict:
    if data.get("schema") != STRIX_ATTESTATION_SCHEMA:
        raise StrixRunnerAttestationError(
            "Strix runner manifest schema mismatch"
        )
    if data.get("version") != STRIX_RELEASE_VERSION:
        raise StrixRunnerAttestationError(
            "Strix runner manifest version mismatch"
        )
    if data.get("source_commit") != STRIX_RELEASE_COMMIT:
        raise StrixRunnerAttestationError(
            "Strix runner source commit mismatch"
        )
    if data.get("cli_version") != f"strix {STRIX_RELEASE_VERSION}":
        raise StrixRunnerAttestationError(
            "Strix runner CLI version mismatch"
        )
    if data.get("platform") != "linux":
        raise StrixRunnerAttestationError(
            "Strix runner platform mismatch"
        )

    architecture = str(data.get("architecture") or "")
    release = _RELEASES.get(architecture)
    if release is None:
        raise StrixRunnerAttestationError(
            "Strix runner architecture is unsupported"
        )
    if data.get("asset_name") != release["asset_name"]:
        raise StrixRunnerAttestationError(
            "Strix runner release asset mismatch"
        )
    if data.get("archive_sha256") != release["archive_sha256"]:
        raise StrixRunnerAttestationError(
            "Strix runner archive digest mismatch"
        )

    binary_sha256 = str(data.get("binary_sha256") or "")
    if (
        len(binary_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in binary_sha256)
    ):
        raise StrixRunnerAttestationError(
            "Strix runner binary digest is invalid"
        )
    return release


def attest_strix_runner(
    *,
    binary_path: str | Path = "/opt/strix/strix",
    manifest_path: str | Path = "/opt/strix/manifest.json",
) -> dict:
    binary = Path(binary_path)
    manifest = Path(manifest_path)
    data = _read_manifest(manifest)
    _validate_manifest(data)

    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise StrixRunnerAttestationError(
            "Strix runner binary is unavailable"
        )
    actual_binary_sha256 = _sha256_file(binary)
    if actual_binary_sha256 != data["binary_sha256"]:
        raise StrixRunnerAttestationError(
            "Strix runner binary digest mismatch"
        )

    cli_version = str(data["cli_version"])

    docker_socket_present = _docker_socket_present()
    if docker_socket_present:
        raise StrixRunnerAttestationError(
            "Strix runner Docker socket must not be present"
        )
    if os.environ.get("DOCKER_HOST"):
        raise StrixRunnerAttestationError(
            "Strix runner Docker host must not be configured"
        )

    active_raw = os.getenv(
        "XBOW_STRIX_ACTIVE_EXECUTION",
        "false",
    ).strip().lower()
    if active_raw not in {"0", "false", "no", "off"}:
        raise StrixRunnerAttestationError(
            "Strix runner active execution must remain disabled"
        )

    return {
        "schema": STRIX_ATTESTATION_SCHEMA,
        "ready": True,
        "version": STRIX_RELEASE_VERSION,
        "source_commit": STRIX_RELEASE_COMMIT,
        "asset_name": data["asset_name"],
        "archive_sha256": data["archive_sha256"],
        "binary_sha256": actual_binary_sha256,
        "cli_version": cli_version,
        "archive_verified": True,
        "binary_verified": True,
        "docker_socket_present": False,
        "docker_host_configured": False,
        "active_execution_enabled": False,
        "network_mode": "internal_only",
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--idle", action="store_true")
    args = parser.parse_args()

    attestation = attest_strix_runner()
    print(
        json.dumps(
            attestation,
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )
    if args.check:
        return 0

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    raise SystemExit(_main())
