from __future__ import annotations

import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .pentagi_adapter import PentagiFlowPlan
from .pentagi_auth import PentagiAuthError, load_pentagi_auth
from .pentagi_execution_guard import PentagiExecutionPermit


class PentagiTransportError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PentagiTransportError("PentAGI transport refused HTTP redirect")


@dataclass(frozen=True)
class PentagiTransportResponse:
    status: int
    body: dict[str, Any]


def _timeout_seconds() -> float:
    raw = (os.getenv("XBOW_PENTAGI_TIMEOUT_SECONDS") or "10").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise PentagiTransportError("XBOW_PENTAGI_TIMEOUT_SECONDS must be numeric") from exc
    if not 1.0 <= value <= 60.0:
        raise PentagiTransportError("PentAGI timeout must be between 1 and 60 seconds")
    return value


def _max_response_bytes() -> int:
    raw = (os.getenv("XBOW_PENTAGI_MAX_RESPONSE_BYTES") or str(1024 * 1024)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise PentagiTransportError("XBOW_PENTAGI_MAX_RESPONSE_BYTES must be an integer") from exc
    if not 1024 <= value <= 8 * 1024 * 1024:
        raise PentagiTransportError("PentAGI response limit must be between 1 KiB and 8 MiB")
    return value


def _validate_endpoint(endpoint: str) -> None:
    try:
        parsed = urlparse(endpoint)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError as exc:
        raise PentagiTransportError("PentAGI endpoint is invalid") from exc

    if parsed.scheme.lower() != "https":
        raise PentagiTransportError("PentAGI endpoint must use HTTPS")
    if not hostname:
        raise PentagiTransportError("PentAGI endpoint has no hostname")
    if username or password:
        raise PentagiTransportError("PentAGI endpoint must not contain credentials")
    if port is not None and not 1 <= port <= 65535:
        raise PentagiTransportError("PentAGI endpoint port is invalid")
    if parsed.query or parsed.fragment:
        raise PentagiTransportError("PentAGI endpoint must not contain query or fragment")
    if parsed.path != "/api/v1/graphql":
        raise PentagiTransportError("PentAGI endpoint path is not the expected GraphQL endpoint")


def _set_response_timeout(response, timeout: float) -> None:
    candidates = (
        getattr(response, "fp", None),
        getattr(getattr(response, "fp", None), "raw", None),
        getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None),
    )
    for candidate in reversed(candidates):
        if candidate is not None and hasattr(candidate, "settimeout"):
            candidate.settimeout(timeout)
            return
    raise PentagiTransportError("PentAGI response socket deadline cannot be enforced")


def _read_bounded_with_deadline(response, *, limit: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PentagiTransportError("PentAGI transport total deadline exceeded")
        _set_response_timeout(response, remaining)
        chunk = response.read(min(65536, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise PentagiTransportError("PentAGI response exceeds configured size limit")
    return b"".join(chunks)


def submit_pentagi_flow(
    plan: PentagiFlowPlan,
    permit: PentagiExecutionPermit,
) -> PentagiTransportResponse:
    """Submit one already-admitted PentAGI GraphQL request.

    The queue must not automatically retry this mutating create operation until
    the remote API exposes a documented idempotency/reconciliation mechanism.
    """

    if plan.dry_run or not plan.execution_supported:
        raise PentagiTransportError("PentAGI plan is not execution-capable")
    if permit.endpoint != plan.endpoint:
        raise PentagiTransportError("PentAGI permit endpoint mismatch")
    if permit.model_provider != plan.model_provider:
        raise PentagiTransportError("PentAGI permit provider mismatch")

    _validate_endpoint(plan.endpoint)

    try:
        body = json.dumps(
            plan.payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PentagiTransportError("PentAGI request is not JSON serializable") from exc

    if len(body) > 128 * 1024:
        raise PentagiTransportError("PentAGI request exceeds 128 KiB")

    try:
        auth = load_pentagi_auth()
    except PentagiAuthError as exc:
        raise PentagiTransportError("PentAGI API token is unavailable") from exc

    headers = auth.headers()
    headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "xbow-perso/pentagi-transport",
            "X-XBOW-Request-Key": permit.idempotency_key,
        }
    )
    request = urllib.request.Request(
        plan.endpoint,
        data=body,
        method="POST",
        headers=headers,
    )

    context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )

    timeout = _timeout_seconds()
    deadline = time.monotonic() + timeout

    try:
        response = opener.open(request, timeout=timeout)
        status = int(getattr(response, "status", response.getcode()))
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "application/json" not in content_type:
            raise PentagiTransportError("PentAGI response is not JSON")
        raw = _read_bounded_with_deadline(
            response,
            limit=_max_response_bytes(),
            deadline=deadline,
        )
    except PentagiTransportError:
        raise
    except urllib.error.HTTPError as exc:
        raise PentagiTransportError(f"PentAGI returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise PentagiTransportError("PentAGI transport connection failed") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise PentagiTransportError("PentAGI transport timed out") from exc
    except OSError as exc:
        raise PentagiTransportError("PentAGI transport I/O failed") from exc

    if status < 200 or status >= 300:
        raise PentagiTransportError(f"PentAGI returned HTTP {status}")

    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PentagiTransportError("PentAGI response contains invalid JSON") from exc
    if not isinstance(document, dict):
        raise PentagiTransportError("PentAGI response must be a JSON object")
    if document.get("errors"):
        raise PentagiTransportError("PentAGI GraphQL response contains errors")
    data = document.get("data")
    if not isinstance(data, dict):
        raise PentagiTransportError("PentAGI GraphQL response has no data object")
    create_flow = data.get("createFlow")
    if not isinstance(create_flow, dict):
        raise PentagiTransportError("PentAGI GraphQL response has no createFlow object")
    flow_id = create_flow.get("id")
    status_value = create_flow.get("status")
    if not isinstance(flow_id, str) or not flow_id.strip():
        raise PentagiTransportError("PentAGI createFlow id is invalid")
    if status_value is not None and not isinstance(status_value, str):
        raise PentagiTransportError("PentAGI createFlow status is invalid")

    return PentagiTransportResponse(status=status, body=document)
