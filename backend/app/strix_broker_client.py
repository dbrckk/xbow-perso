from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import ValidationError

from .strix_broker_models import BrokerHttpRequest, BrokerHttpResponse


class StrixBrokerClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502):
        self.status_code = status_code
        super().__init__(message)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class EgressEndpoint:
    url: str
    host: str
    port: int


def _egress_endpoint() -> EgressEndpoint:
    raw = os.getenv(
        "XBOW_STRIX_EGRESS_URL",
        "http://strix-egress:8091/v1/fetch",
    ).strip()
    parsed = urlsplit(raw)
    try:
        port = parsed.port
    except ValueError as exc:
        raise StrixBrokerClientError(
            "Strix egress service URL is invalid",
            status_code=503,
        ) from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "strix-egress"
        or port not in {None, 8091}
        or parsed.path != "/v1/fetch"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise StrixBrokerClientError(
            "Strix egress service URL is not the isolated internal endpoint",
            status_code=503,
        )
    return EgressEndpoint(
        url=raw,
        host="strix-egress",
        port=port or 8091,
    )


def _timeout_seconds() -> float:
    raw = os.getenv("XBOW_STRIX_BROKER_EGRESS_TIMEOUT_SECONDS", "15")
    try:
        value = float(raw)
    except ValueError as exc:
        raise StrixBrokerClientError(
            "XBOW_STRIX_BROKER_EGRESS_TIMEOUT_SECONDS must be a number",
            status_code=503,
        ) from exc
    if not math.isfinite(value) or not 1.0 <= value <= 30.0:
        raise StrixBrokerClientError(
            "XBOW_STRIX_BROKER_EGRESS_TIMEOUT_SECONDS must be between 1 and 30",
            status_code=503,
        )
    return value


def _opener():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )


def forward_read_only_request(
    request: BrokerHttpRequest,
) -> BrokerHttpResponse:
    endpoint = _egress_endpoint()
    payload = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    outbound = urllib.request.Request(
        endpoint.url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "xbow-strix-broker/1.0",
        },
    )
    try:
        with _opener().open(
            outbound,
            timeout=_timeout_seconds(),
        ) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise StrixBrokerClientError(
                    "Strix egress service response exceeded size limit"
                )
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        if status in {403, 429, 503}:
            raise StrixBrokerClientError(
                "Strix egress service rejected the request",
                status_code=status,
            ) from exc
        raise StrixBrokerClientError(
            "Strix egress service failed",
            status_code=502,
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise StrixBrokerClientError(
            "Strix egress service is unavailable",
            status_code=502,
        ) from exc

    if status != 200:
        raise StrixBrokerClientError(
            "Strix egress service returned an unexpected status",
            status_code=502,
        )
    try:
        decoded = json.loads(raw.decode("utf-8"))
        return BrokerHttpResponse.model_validate(decoded)
    except (UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise StrixBrokerClientError(
            "Strix egress service returned an invalid response",
            status_code=502,
        ) from exc
