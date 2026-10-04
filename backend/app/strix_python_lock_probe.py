from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


STRIX_PYTHON_LOCK_SCHEMA = "strix-python-lock-probe-v1"
STRIX_SOURCE_COMMIT = "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2"
STRIX_VERSION = "1.6.2"
STRIX_PYPROJECT_GIT_BLOB_SHA1 = "b78fb3aa90936edaedc86cf634d34de89bcb9f5b"
STRIX_UV_LOCK_GIT_BLOB_SHA1 = "2cb4cb5f0c4732dce1dc3cca21406ae63f66b148"
STRIX_PYTHON_REQUIREMENT = ">=3.12"
STRIX_UV_LOCK_VERSION = 1
STRIX_UV_LOCK_REVISION = 3
_MAX_LOCK_SOURCE_BYTES = 1024 * 1024
_EXPECTED_DIRECT_DEPENDENCIES = (
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
)


class StrixPythonLockError(RuntimeError):
    pass


def _read_bounded_bytes(path: Path) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise StrixPythonLockError(
            "Strix dependency source is unreadable"
        ) from exc
    if len(payload) > _MAX_LOCK_SOURCE_BYTES:
        raise StrixPythonLockError(
            "Strix dependency source size exceeds limit"
        )
    return payload


def _git_blob_sha1(path: Path) -> str:
    payload = _read_bounded_bytes(path)
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(
        header + payload,
        usedforsecurity=False,
    ).hexdigest()


def _read_toml(path: Path) -> dict[str, Any]:
    payload = _read_bounded_bytes(path)
    try:
        parsed = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise StrixPythonLockError(
            "Strix dependency source TOML is invalid"
        ) from exc
    if not isinstance(parsed, dict):
        raise StrixPythonLockError(
            "Strix dependency source TOML is invalid"
        )
    return parsed


def _find_strix_package(lock: dict[str, Any]) -> dict[str, Any]:
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise StrixPythonLockError(
            "Strix dependency lock packages are invalid"
        )
    matches = [
        package
        for package in packages
        if isinstance(package, dict)
        and package.get("name") == "strix-agent"
    ]
    if len(matches) != 1:
        raise StrixPythonLockError(
            "Strix dependency lock package entry is invalid"
        )
    return matches[0]


def probe_dependency_lock(
    *,
    pyproject_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    pyproject_blob = _git_blob_sha1(pyproject_path)
    lock_blob = _git_blob_sha1(lock_path)
    if (
        pyproject_blob != STRIX_PYPROJECT_GIT_BLOB_SHA1
        or lock_blob != STRIX_UV_LOCK_GIT_BLOB_SHA1
    ):
        raise StrixPythonLockError(
            "Strix dependency source identity changed"
        )

    pyproject = _read_toml(pyproject_path)
    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise StrixPythonLockError(
            "Strix pyproject metadata is invalid"
        )
    if (
        project.get("name") != "strix-agent"
        or project.get("version") != STRIX_VERSION
        or project.get("requires-python") != STRIX_PYTHON_REQUIREMENT
    ):
        raise StrixPythonLockError(
            "Strix pyproject metadata changed"
        )

    lock = _read_toml(lock_path)
    if (
        lock.get("version") != STRIX_UV_LOCK_VERSION
        or lock.get("revision") != STRIX_UV_LOCK_REVISION
        or lock.get("requires-python") != STRIX_PYTHON_REQUIREMENT
    ):
        raise StrixPythonLockError(
            "Strix dependency lock metadata changed"
        )

    package = _find_strix_package(lock)
    if (
        package.get("version") != STRIX_VERSION
        or package.get("source") != {"editable": "."}
    ):
        raise StrixPythonLockError(
            "Strix dependency lock package entry changed"
        )

    dependencies = package.get("dependencies")
    if not isinstance(dependencies, list):
        raise StrixPythonLockError(
            "Strix dependency lock dependencies are invalid"
        )
    names = sorted(
        item.get("name")
        for item in dependencies
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
    )
    if names != sorted(_EXPECTED_DIRECT_DEPENDENCIES):
        raise StrixPythonLockError(
            "Strix dependency lock direct dependencies changed"
        )

    return {
        "schema": STRIX_PYTHON_LOCK_SCHEMA,
        "source_commit": STRIX_SOURCE_COMMIT,
        "strix_version": STRIX_VERSION,
        "python_requirement": STRIX_PYTHON_REQUIREMENT,
        "uv_lock_version": STRIX_UV_LOCK_VERSION,
        "uv_lock_revision": STRIX_UV_LOCK_REVISION,
        "pyproject_blob_sha1": pyproject_blob,
        "uv_lock_blob_sha1": lock_blob,
        "direct_dependency_count": len(names),
        "dependency_lock_attested": True,
        "runtime_install_enabled": False,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--pyproject", type=Path)
    parser.add_argument("--lock", type=Path)
    args = parser.parse_args()
    if not args.self_test or args.pyproject is None or args.lock is None:
        raise StrixPythonLockError(
            "only --self-test with --pyproject and --lock is supported"
        )
    sys.stdout.write(
        json.dumps(
            probe_dependency_lock(
                pyproject_path=args.pyproject,
                lock_path=args.lock,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
