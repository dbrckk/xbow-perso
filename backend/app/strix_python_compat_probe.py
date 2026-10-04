from __future__ import annotations

import argparse
import hashlib
import json
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from .strix_backend_hook import (
    STRIX_BACKEND_NAME,
    STRIX_EXPECTED_VERSION,
    register_xbow_backend,
)


STRIX_PYTHON_COMPAT_SCHEMA = "strix-python-compat-probe-v1"
STRIX_MAIN_PY_GIT_BLOB_SHA1 = "c9bd559614a4b6a952229500721216be6df50c62"
STRIX_ENVIRONMENT_PY_GIT_BLOB_SHA1 = "522067df84a046379341f0e243dea57c9205b6b1"
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


def _upstream_source_path(relative_path: str) -> Path:
    try:
        distribution = metadata.distribution("strix-agent")
    except metadata.PackageNotFoundError as exc:
        raise StrixPythonCompatError(
            "pinned Strix Python package is unavailable"
        ) from exc

    for item in distribution.files or ():
        if item.as_posix() == relative_path:
            return Path(distribution.locate_file(item))
    raise StrixPythonCompatError(
        "required Strix upstream source is unavailable"
    )


def _upstream_main_path() -> Path:
    return _upstream_source_path("strix/interface/main.py")


def _read_bounded_bytes(path: Path) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise StrixPythonCompatError(
            "Strix upstream source is unreadable"
        ) from exc
    if len(payload) > _MAX_UPSTREAM_SOURCE_BYTES:
        raise StrixPythonCompatError(
            "Strix upstream source size exceeds limit"
        )
    return payload


def _git_blob_sha1(path: Path) -> str:
    payload = _read_bounded_bytes(path)
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(
        header + payload,
        usedforsecurity=False,
    ).hexdigest()


def _read_upstream_main_source(path: Path) -> str:
    payload = _read_bounded_bytes(path)
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

    main_path = _upstream_source_path("strix/interface/main.py")
    environment_path = _upstream_source_path(
        "strix/interface/environment.py"
    )
    main_blob_sha1 = _git_blob_sha1(main_path)
    environment_blob_sha1 = _git_blob_sha1(environment_path)
    if (
        main_blob_sha1 != STRIX_MAIN_PY_GIT_BLOB_SHA1
        or environment_blob_sha1 != STRIX_ENVIRONMENT_PY_GIT_BLOB_SHA1
    ):
        raise StrixPythonCompatError(
            "Strix upstream source identity changed"
        )

    source = _read_upstream_main_source(main_path)
    _verify_docker_preflight(source)

    return {
        "schema": STRIX_PYTHON_COMPAT_SCHEMA,
        "strix_version": version,
        "backend": STRIX_BACKEND_NAME,
        "hook_loaded_in_python_runtime": True,
        "supports_bind_mounts": False,
        "active_execution_enabled": False,
        "upstream_docker_preflight_required": True,
        "entrypoint_enabled": False,
        "upstream_main_blob_sha1": main_blob_sha1,
        "upstream_environment_blob_sha1": environment_blob_sha1,
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
