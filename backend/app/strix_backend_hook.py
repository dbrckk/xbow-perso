from __future__ import annotations

import argparse
import asyncio
import json
import os
from importlib import metadata
from typing import Any


STRIX_BACKEND_NAME = "xbow-remote-v1"
STRIX_EXPECTED_VERSION = "1.6.2"
STRIX_SOURCE_COMMIT = "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2"
STRIX_X86_64_WHEEL_SHA256 = (
    "1a93fbf0f18fad6bf4802c41fa5e032ce50880a655fddee47f6bec4f1ea2155b"
)


class StrixBackendHookError(RuntimeError):
    pass


class StrixBackendBlocked(StrixBackendHookError):
    pass


async def _blocked_backend(
    *,
    image: str,
    manifest: Any,
    exposed_ports: tuple[int, ...],
    bind_mounts: list[dict[str, Any]] | None = None,
) -> tuple[Any, Any]:
    del image, manifest, exposed_ports, bind_mounts
    raise StrixBackendBlocked(
        "xbow Strix backend is registered but remote execution is not wired"
    )


def _installed_strix_version() -> str:
    try:
        return metadata.version("strix-agent")
    except metadata.PackageNotFoundError as exc:
        raise StrixBackendHookError(
            "pinned Strix Python package is unavailable"
        ) from exc


def _backend_api():
    try:
        from strix.runtime.backends import (
            backend_supports_bind_mounts,
            get_backend,
            register_backend,
            supported_backends,
        )
    except ImportError as exc:
        raise StrixBackendHookError(
            "Strix runtime backend API is unavailable"
        ) from exc
    return (
        register_backend,
        get_backend,
        supported_backends,
        backend_supports_bind_mounts,
    )


def register_xbow_backend() -> dict[str, Any]:
    (
        register_backend,
        get_backend,
        supported_backends,
        backend_supports_bind_mounts,
    ) = _backend_api()

    supported = set(supported_backends())
    if STRIX_BACKEND_NAME in supported:
        existing = get_backend(STRIX_BACKEND_NAME)
        if existing is not _blocked_backend:
            raise StrixBackendHookError(
                "Strix backend name collision for xbow-remote-v1"
            )
    else:
        register_backend(
            STRIX_BACKEND_NAME,
            _blocked_backend,
            supports_bind_mounts=False,
        )

    selected = get_backend(STRIX_BACKEND_NAME)
    if selected is not _blocked_backend:
        raise StrixBackendHookError(
            "Strix backend registry returned an unexpected backend"
        )
    if backend_supports_bind_mounts(STRIX_BACKEND_NAME):
        raise StrixBackendHookError(
            "xbow remote backend must not support host bind mounts"
        )

    os.environ["STRIX_RUNTIME_BACKEND"] = STRIX_BACKEND_NAME
    return {
        "backend": STRIX_BACKEND_NAME,
        "registered": True,
        "supports_bind_mounts": False,
        "active_execution_enabled": False,
    }


async def _assert_backend_fails_closed() -> None:
    _, get_backend, _, _ = _backend_api()
    backend = get_backend(STRIX_BACKEND_NAME)
    try:
        await backend(
            image="unused",
            manifest=object(),
            exposed_ports=(),
            bind_mounts=[],
        )
    except StrixBackendBlocked:
        return
    raise StrixBackendHookError(
        "xbow Strix backend did not fail closed"
    )


def self_test() -> dict[str, Any]:
    version = _installed_strix_version()
    if version != STRIX_EXPECTED_VERSION:
        raise StrixBackendHookError(
            "unexpected Strix version: "
            f"{version!r} != {STRIX_EXPECTED_VERSION!r}"
        )
    descriptor = register_xbow_backend()
    asyncio.run(_assert_backend_fails_closed())
    return {
        "schema": "strix-backend-hook-v1",
        "strix_version": version,
        "source_commit": STRIX_SOURCE_COMMIT,
        "wheel_sha256": STRIX_X86_64_WHEEL_SHA256,
        **descriptor,
        "fail_closed_verified": True,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        raise StrixBackendHookError(
            "only --self-test is supported until remote execution is wired"
        )
    print(
        json.dumps(
            self_test(),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
