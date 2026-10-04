from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


STRIX_PYTHON_TOOLCHAIN_SCHEMA = "strix-python-runtime-lock-v1"
STRIX_SOURCE_COMMIT = "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2"
STRIX_VERSION = "1.6.2"
STRIX_RELEASE_PYTHON_VERSION = "3.12.14"
STRIX_RELEASE_UV_VERSION = "0.12.10"
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_UV_ARCHIVE_BYTES = 64 * 1024 * 1024


class StrixPythonToolchainError(RuntimeError):
    pass


def _read_bounded(path: Path, limit: int) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise StrixPythonToolchainError(
            "Strix Python toolchain input is unreadable"
        ) from exc
    if len(payload) > limit:
        raise StrixPythonToolchainError(
            "Strix Python toolchain input exceeds size limit"
        )
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(
        _read_bounded(path, _MAX_UV_ARCHIVE_BYTES)
    ).hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = _read_bounded(path, _MAX_MANIFEST_BYTES)
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StrixPythonToolchainError(
            "Strix Python toolchain manifest is invalid"
        ) from exc
    if not isinstance(decoded, dict):
        raise StrixPythonToolchainError(
            "Strix Python toolchain manifest is invalid"
        )
    return decoded


def probe_toolchain(
    *,
    manifest_path: Path,
    uv_archive_path: Path,
    architecture: str,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    if (
        manifest.get("schema") != STRIX_PYTHON_TOOLCHAIN_SCHEMA
        or manifest.get("source_commit") != STRIX_SOURCE_COMMIT
        or manifest.get("strix_version") != STRIX_VERSION
        or manifest.get("runtime_install_enabled") is not False
        or manifest.get("active_execution_enabled") is not False
    ):
        raise StrixPythonToolchainError(
            "Strix Python toolchain manifest contract changed"
        )

    release_build = manifest.get("release_build")
    if not isinstance(release_build, dict):
        raise StrixPythonToolchainError(
            "Strix Python release build metadata is invalid"
        )
    if (
        release_build.get("python_version")
        != STRIX_RELEASE_PYTHON_VERSION
        or release_build.get("uv_version") != STRIX_RELEASE_UV_VERSION
    ):
        raise StrixPythonToolchainError(
            "Strix Python release build metadata changed"
        )

    assets = manifest.get("uv_assets")
    if not isinstance(assets, dict):
        raise StrixPythonToolchainError(
            "Strix uv asset metadata is invalid"
        )
    asset = assets.get(architecture)
    if not isinstance(asset, dict):
        raise StrixPythonToolchainError(
            "Strix uv architecture is unsupported"
        )
    asset_name = asset.get("asset")
    expected_sha256 = asset.get("sha256")
    if (
        not isinstance(asset_name, str)
        or not asset_name
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
    ):
        raise StrixPythonToolchainError(
            "Strix uv asset metadata is invalid"
        )

    observed_sha256 = _sha256_file(uv_archive_path)
    if observed_sha256 != expected_sha256:
        raise StrixPythonToolchainError(
            "Strix uv archive digest mismatch"
        )

    return {
        "schema": STRIX_PYTHON_TOOLCHAIN_SCHEMA,
        "source_commit": STRIX_SOURCE_COMMIT,
        "strix_version": STRIX_VERSION,
        "python_version": STRIX_RELEASE_PYTHON_VERSION,
        "uv_version": STRIX_RELEASE_UV_VERSION,
        "architecture": architecture,
        "uv_asset": asset_name,
        "uv_sha256": observed_sha256,
        "toolchain_attested": True,
        "runtime_install_enabled": False,
        "active_execution_enabled": False,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--uv-archive", type=Path)
    parser.add_argument("--architecture")
    args = parser.parse_args()
    if (
        not args.self_test
        or args.manifest is None
        or args.uv_archive is None
        or not args.architecture
    ):
        raise StrixPythonToolchainError(
            "only --self-test with manifest, uv archive, and architecture "
            "is supported"
        )
    sys.stdout.write(
        json.dumps(
            probe_toolchain(
                manifest_path=args.manifest,
                uv_archive_path=args.uv_archive,
                architecture=args.architecture,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
