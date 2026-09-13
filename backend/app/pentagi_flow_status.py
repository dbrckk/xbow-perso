from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

from .pentagi_auth import PentagiAuthError, load_pentagi_auth
from .pentagi_transport import (
    PentagiTransportError,
    _NoRedirect,
    _max_response_bytes,
    _read_bounded_with_deadline,
    _timeout_seconds,
)

_ALLOWED_FLOW_STATUSES = {"created", "running", "waiting", "finished", "failed"}


@dataclass(frozen=True)
class PentagiFlowStatus:
    flow_id: str
    status: str
    title: str | None
    body: dict[str, Any]


def _flow_status_url(graphql_endpoint: str, flow_id: str) -> str:
    flow_id = flow_id.strip()
    if not flow_id or len(flow_id) > 200:
        raise PentagiTransportError("PentAGI flow id is invalid")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in flow_id):
        raise PentagiTransportError("PentAGI flow id is invalid")

    try:
        parsed = urlparse(graphql_endpoint)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError as exc:
        raise PentagiTransportError("PentAGI endpoint is invalid") from exc

    if parsed.scheme.lower() != "https" or not hostname:
        raise PentagiTransportError("PentAGI endpoint must use HTTPS")
    if username or password:
        raise PentagiTransportError("PentAGI endpoint must not contain credentials")
    if port is not None and not 1 <= port <= 65535:
        raise PentagiTransportError("PentAGI endpoint port is invalid")
    if parsed.query or parsed.fragment or parsed.path != "/api/v1/graphql":
        raise PentagiTransportError("PentAGI endpoint is not the expected GraphQL endpoint")

    authority = hostname
    if ":" in hostname and not hostname.startswith("["):
        authority = f"[{hostname}]"
    if port is not None:
        authority = f"{authority}:{port}"
    return f"https://{authority}/api/v1/flows/{quote(flow_id, safe='')}"


def fetch_pentagi_flow_status(
    graphql_endpoint: str,
    flow_id: str,
    *,
    timeout_seconds: float | None = None,
) -> PentagiFlowStatus:
    """Fetch one existing PentAGI flow without mutating remote state."""

    url = _flow_status_url(graphql_endpoint, flow_id)
    try:
        auth = load_pentagi_auth()
    except PentagiAuthError as exc:
        raise PentagiTransportError("PentAGI API token is unavailable") from exc

    headers = auth.headers()
    headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "xbow-perso/pentagi-status",
        }
    )
    request = urllib.request.Request(url, method="GET", headers=headers)
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        _NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )

    configured_timeout = _timeout_seconds()
    if timeout_seconds is None:
        timeout = configured_timeout
    else:
        try:
            requested_timeout = float(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise PentagiTransportError("PentAGI flow status timeout is invalid") from exc
        if requested_timeout <= 0:
            raise PentagiTransportError("PentAGI flow status timeout must be positive")
        timeout = min(configured_timeout, requested_timeout)
    deadline = time.monotonic() + timeout
    try:
        response = opener.open(request, timeout=timeout)
        status_code = int(getattr(response, "status", response.getcode()))
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "application/json" not in content_type:
            raise PentagiTransportError("PentAGI flow status response is not JSON")
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
        raise PentagiTransportError("PentAGI flow status connection failed") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise PentagiTransportError("PentAGI flow status request timed out") from exc
    except OSError as exc:
        raise PentagiTransportError("PentAGI flow status I/O failed") from exc

    if status_code < 200 or status_code >= 300:
        raise PentagiTransportError(f"PentAGI returned HTTP {status_code}")

    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PentagiTransportError("PentAGI flow status contains invalid JSON") from exc
    if not isinstance(document, dict):
        raise PentagiTransportError("PentAGI flow status must be a JSON object")

    remote_id = document.get("id")
    remote_status = document.get("status")
    title = document.get("title")
    if not isinstance(remote_id, str) or remote_id != flow_id:
        raise PentagiTransportError("PentAGI flow status id mismatch")
    if not isinstance(remote_status, str) or remote_status not in _ALLOWED_FLOW_STATUSES:
        raise PentagiTransportError("PentAGI flow status is invalid")
    if title is not None and not isinstance(title, str):
        raise PentagiTransportError("PentAGI flow title is invalid")

    return PentagiFlowStatus(
        flow_id=remote_id,
        status=remote_status,
        title=title,
        body=document,
    )
