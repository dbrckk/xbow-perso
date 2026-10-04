from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request

from .strix_runner_attestation import (
    STRIX_RELEASE_COMMIT,
    STRIX_RELEASE_VERSION,
)
from .strix_runner_rpc import RUNNER_RPC_PROTOCOL


RUNNER_READINESS_URL = "http://strix-runner:8092/readyz"
RUNNER_READINESS_TIMEOUT_SECONDS = 5.0
RUNNER_READINESS_MAX_BYTES = 4096

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StrixRunnerClientError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )


def _validate_readiness(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise StrixRunnerClientError(
            "Strix runner readiness posture is invalid"
        )

    binary_sha256 = payload.get("binary_sha256")
    expected = {
        "status": "ready",
        "protocol": RUNNER_RPC_PROTOCOL,
        "active_execution_enabled": False,
        "implemented_operations": [],
        "runner_attested": True,
        "runner_version": STRIX_RELEASE_VERSION,
        "source_commit": STRIX_RELEASE_COMMIT,
    }
    if (
        any(payload.get(key) != value for key, value in expected.items())
        or not isinstance(binary_sha256, str)
        or not _SHA256_RE.fullmatch(binary_sha256)
    ):
        raise StrixRunnerClientError(
            "Strix runner readiness posture is unexpected"
        )

    return {
        "ready": True,
        "protocol": RUNNER_RPC_PROTOCOL,
        "runner_version": STRIX_RELEASE_VERSION,
        "source_commit": STRIX_RELEASE_COMMIT,
        "binary_sha256": binary_sha256,
        "active_execution_enabled": False,
        "implemented_operations": [],
    }


def check_runner_readiness() -> dict:
    request = urllib.request.Request(
        RUNNER_READINESS_URL,
        method="GET",
        headers={
            "Accept": "application/json",
            "User-Agent": "xbow-strix-runner-readiness/1.0",
        },
    )
    try:
        with _opener().open(
            request,
            timeout=RUNNER_READINESS_TIMEOUT_SECONDS,
        ) as response:
            payload = response.read(RUNNER_READINESS_MAX_BYTES + 1)
            if int(response.status) != 200:
                raise StrixRunnerClientError(
                    "Strix runner readiness returned an unexpected status"
                )
            if len(payload) > RUNNER_READINESS_MAX_BYTES:
                raise StrixRunnerClientError(
                    "Strix runner readiness response exceeded size limit"
                )
    except urllib.error.HTTPError as exc:
        raise StrixRunnerClientError(
            "Strix runner readiness was rejected"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise StrixRunnerClientError(
            "Strix runner readiness service is unavailable"
        ) from exc

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StrixRunnerClientError(
            "Strix runner readiness response is invalid"
        ) from exc
    return _validate_readiness(decoded)


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-readiness", action="store_true")
    args = parser.parse_args()
    if not args.check_readiness:
        raise StrixRunnerClientError(
            "only --check-readiness is supported"
        )
    print(
        json.dumps(
            check_runner_readiness(),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
