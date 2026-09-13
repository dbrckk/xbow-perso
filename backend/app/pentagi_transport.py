from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .pentagi_adapter import PentagiFlowPlan
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


def _token() -> str:
    value = (os.getenv("XBOW_PENTAGI_TOKEN") or "").strip()
    if not value:
        raise PentagiTransportError("XBOW_PENTAGI_TOKEN is required")
    if len(value) > 8192 or any(ord(ch) < 33 or ord(ch) == 127 for ch in value):
        raise PentagiTransportError("XBOW_PENTAGI_TOKEN is invalid")
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


def submit_pentagi_flow(
    plan: PentagiFlowPlan,
    permit: PentagiExecutionPermit,
) -> PentagiTransportResponse:
    """Submit one already-admitted PentAGI GraphQL request.

    This transport deliberately has no retry loop. Retries are owned by the queue
    layer so duplicate execution remains governed by the durable idempotency key.
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

    token = _token()
    request = urllib.request.Request(
        plan.endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "xbow-perso/pentagi-transport",
            "X-XBOW-Idempotency-Key": permit.idempotency_key,
        },
    )

    context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )

    try:
        response = opener.open(request, timeout=_timeout_seconds())
        status = int(getattr(response, "status", response.getcode()))
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "application/json" not in content_type:
            raise PentagiTransportError("PentAGI response is not JSON")

        limit = _max_response_bytes()
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise PentagiTransportError("PentAGI response exceeds configured size limit")
    except PentagiTransportError:
        raise
    except urllib.error.HTTPError as exc:
        # Do not surface remote bodies or request headers; they may contain
        # sensitive service diagnostics or reflect credentials.
        raise PentagiTransportError(f"PentAGI returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise PentagiTransportError("PentAGI transport connection failed") from exc
    except TimeoutError as exc:
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
    if not isinstance(document.get("data"), dict):
        raise PentagiTransportError("PentAGI GraphQL response has no data object")

    return PentagiTransportResponse(status=status, body=document)
