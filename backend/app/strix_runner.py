from __future__ import annotations

import hashlib
import json
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PINNED_STRIX_VERSION = "1.6.2"
PINNED_STRIX_UPSTREAM_COMMIT = "ff5c8cc8e46d8e60c2bc2439f7bcb07c05ca3db2"
PINNED_STRIX_ASSETS = {
    "amd64": {
        "asset": "strix-1.6.2-linux-x86_64.tar.gz",
        "sha256": "f3f29fa64bee420bf64f8911fb9f38e20270d406f6df44cc2436252c2af0bc81",
    },
    "arm64": {
        "asset": "strix-1.6.2-linux-arm64.tar.gz",
        "sha256": "4a4cba115bda8b89d7bbfabe960246a480ff43563144959b2e33477955aa6df2",
    },
}
_MANIFEST_SCHEMA = "xbow-strix-runner-manifest-v1"
_MANIFEST_FIELDS = {
    "schema",
    "version",
    "upstream_commit",
    "architecture",
    "asset",
    "sha256",
}


class StrixRunnerAttestationError(RuntimeError):
    pass


def health_document() -> dict:
    return {
        "status": "ok",
        "mode": "attestation_only",
        "execution_enabled": False,
        "network_access": "internal_only",
        "docker_socket_allowed": False,
        "pinned_version": PINNED_STRIX_VERSION,
    }


def _load_manifest(path: Path) -> dict:
    if path.is_symlink():
        raise StrixRunnerAttestationError("manifest must not be a symlink")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise StrixRunnerAttestationError("runner manifest is unavailable") from exc
    if len(raw) > 16 * 1024:
        raise StrixRunnerAttestationError("runner manifest is too large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StrixRunnerAttestationError("runner manifest is invalid") from exc
    if not isinstance(payload, dict):
        raise StrixRunnerAttestationError("runner manifest must be an object")
    if set(payload) != _MANIFEST_FIELDS:
        raise StrixRunnerAttestationError("runner manifest fields are invalid")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise StrixRunnerAttestationError("runner binary is unreadable") from exc
    return digest.hexdigest()


def _validate_manifest(manifest: dict) -> dict:
    if manifest["schema"] != _MANIFEST_SCHEMA:
        raise StrixRunnerAttestationError("runner manifest schema is unsupported")
    if manifest["version"] != PINNED_STRIX_VERSION:
        raise StrixRunnerAttestationError("runner manifest version is not pinned")
    if manifest["upstream_commit"] != PINNED_STRIX_UPSTREAM_COMMIT:
        raise StrixRunnerAttestationError(
            "runner manifest upstream commit is not pinned"
        )

    architecture = str(manifest["architecture"])
    pinned = PINNED_STRIX_ASSETS.get(architecture)
    if pinned is None:
        raise StrixRunnerAttestationError(
            "runner manifest architecture is unsupported"
        )
    if manifest["asset"] != pinned["asset"]:
        raise StrixRunnerAttestationError("runner manifest asset is not pinned")
    if manifest["sha256"] != pinned["sha256"]:
        raise StrixRunnerAttestationError("runner manifest sha256 is not pinned")
    return pinned


def attest_strix_runtime(
    *,
    binary_path: Path | str = "/opt/strix/strix",
    manifest_path: Path | str = "/opt/strix/manifest.json",
) -> dict:
    binary = Path(binary_path)
    manifest_file = Path(manifest_path)
    manifest = _load_manifest(manifest_file)
    _validate_manifest(manifest)

    if binary.is_symlink():
        raise StrixRunnerAttestationError("runner binary must not be a symlink")
    if not binary.is_file():
        raise StrixRunnerAttestationError("runner binary is unavailable")
    if not os.access(binary, os.X_OK):
        raise StrixRunnerAttestationError("runner binary is not executable")

    actual_sha256 = _sha256_file(binary)
    if actual_sha256 != manifest["sha256"]:
        raise StrixRunnerAttestationError("runner binary sha256 mismatch")

    try:
        completed = subprocess.run(
            [str(binary), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            env={
                "HOME": "/tmp",
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
            },
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise StrixRunnerAttestationError(
            "runner binary version probe failed"
        ) from exc

    expected_version = f"strix {PINNED_STRIX_VERSION}"
    if completed.stdout.strip() != expected_version:
        raise StrixRunnerAttestationError("runner runtime version mismatch")

    return {
        "status": "ready",
        "mode": "attestation_only",
        "execution_enabled": False,
        "network_access": "internal_only",
        "docker_socket_allowed": False,
        "version": PINNED_STRIX_VERSION,
        "sha256": actual_sha256,
        "upstream_commit": PINNED_STRIX_UPSTREAM_COMMIT,
        "architecture": manifest["architecture"],
        "asset": manifest["asset"],
    }


def _server_host() -> str:
    return os.getenv("XBOW_STRIX_RUNNER_HOST", "0.0.0.0").strip() or "0.0.0.0"


def _server_port() -> int:
    raw = os.getenv("XBOW_STRIX_RUNNER_PORT", "8092").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise StrixRunnerAttestationError(
            "XBOW_STRIX_RUNNER_PORT must be an integer"
        ) from exc
    if not 1 <= value <= 65535:
        raise StrixRunnerAttestationError(
            "XBOW_STRIX_RUNNER_PORT must be between 1 and 65535"
        )
    return value


class StrixRunnerHandler(BaseHTTPRequestHandler):
    server_version = "xbow-strix-runner/1.0"
    sys_version = ""

    def log_message(self, format, *args):
        return

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._write_json(HTTPStatus.OK, health_document())
            return
        if path == "/readyz":
            try:
                payload = attest_strix_runtime()
            except StrixRunnerAttestationError:
                self._write_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "status": "not_ready",
                        "mode": "attestation_only",
                        "execution_enabled": False,
                        "reason": "runtime_attestation_failed",
                    },
                )
                return
            self._write_json(HTTPStatus.OK, payload)
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"status": "not_found"},
        )

    def do_HEAD(self):
        path = urlsplit(self.path).path
        if path not in {"/healthz", "/readyz"}:
            self.send_response(HTTPStatus.NOT_FOUND.value)
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_POST(self):
        self._write_json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"status": "method_not_allowed"},
        )


def main() -> None:
    server = ThreadingHTTPServer(
        (_server_host(), _server_port()),
        StrixRunnerHandler,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
