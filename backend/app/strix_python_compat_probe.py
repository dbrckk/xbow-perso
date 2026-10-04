from __future__ import annotations

import argparse
import json
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from .strix_backend_hook import (
    STRIX_BACKEND_NAME,
    STRIX_EXPECTED_VERSION,
    STRIX_SOURCE_COMMIT,
    register_xbow_backend,
)


STRIX_PYTHON_COMPAT_SCHEMA = "strix-python-compat-probe-v1"
STRIX_UPSTREAM_PYPROJECT_SHA256 = (
    "78e22229485fcd69cf07670812826170"
    "a6538c157e61ccf12aa38661fc066c6c"
)
STRIX_UPSTREAM_UV_LOCK_SHA256 = (
    "b4adb335fdfa72b64173e120eea57d08"
    "b0a993979eb4b01157b2f1488f81c6ea"
)
_MAX_UPSTREAM_SOURCE_BYTES = 512 * 1024
_REQUIRED_DOCKER_PREFLIGHT_MARKERS = (
    "check_docker_installed()",
    "pull_docker_image()",
    "validate_environment()",
)


class StrixPythonCompatError(RuntimeError):
    pass


def _installed_strix_version() -> str:
    try:
        return metadata.version("strix-agent")
    except metadata.PackageNotFoundError as exc:
        raise StrixPythonCompatError(
            "pinned Strix Python package is unavailable"
        ) from exc


def _upstream_main_path() -> Path:
    try:
        distribution = metadata.distribution("strix-agent")
    except metadata.PackageNotFoundError as exc:
        raise StrixPythonCompatError(
            "pinned Strix Python package is unavailable"
        ) from exc

    for item in distribution.files or ():
        if item.as_posix() == "strix/interface/main.py":
            return Path(distribution.locate_file(item))
    raise StrixPythonCompatError(
        "Strix interface main source is unavailable"
    )


def _read_upstream_main_source(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise StrixPythonCompatError(
            "Strix interface main source is unreadable"
        ) from exc
    if len(payload) > _MAX_UPSTREAM_SOURCE_BYTES:
        raise StrixPythonCompatError(
            "Strix interface main source size exceeds limit"
        )
    try:
        return payload.decode("utf-8")
    except UnicodeError as exc:
        raise StrixPythonCompatError(
            "Strix interface main source encoding is invalid"
        ) from exc


def _verify_docker_preflight(source: str) -> None:
    missing = [
        marker
        for marker in _REQUIRED_DOCKER_PREFLIGHT_MARKERS
        if marker not in source
    ]
    if missing:
        raise StrixPythonCompatError(
            "Strix upstream Docker preflight markers changed"
        )


def probe_python_runtime() -> dict[str, Any]:
    version = _installed_strix_version()
    if version != STRIX_EXPECTED_VERSION:
        raise StrixPythonCompatError(
            "unexpected Strix Python package version"
        )

    descriptor = register_xbow_backend()
    expected_descriptor = {
        "backend": STRIX_BACKEND_NAME,
        "registered": True,
        "supports_bind_mounts": False,
        "active_execution_enabled": False,
    }
    if descriptor != expected_descriptor:
        raise StrixPythonCompatError(
            "Strix backend hook descriptor is unexpected"
        )

    source = _read_upstream_main_source(_upstream_main_path())
    _verify_docker_preflight(source)

    return {
        "schema": STRIX_PYTHON_COMPAT_SCHEMA,
        "strix_version": version,
        "backend": STRIX_BACKEND_NAME,
        "hook_loaded_in_python_runtime": True,
        "supports_bind_mounts": False,
        "active_execution_enabled": False,
        "upstream_docker_preflight_required": True,
        "source_commit": STRIX_SOURCE_COMMIT,
        "upstream_pyproject_sha256": STRIX_UPSTREAM_PYPROJECT_SHA256,
        "upstream_uv_lock_sha256": STRIX_UPSTREAM_UV_LOCK_SHA256,
        "dependency_lock_installation_enabled": False,
        "entrypoint_enabled": False,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        raise StrixPythonCompatError(
            "only --self-test is supported"
        )
    sys.stdout.write(
        json.dumps(
            probe_python_runtime(),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
