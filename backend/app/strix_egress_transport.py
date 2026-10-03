from __future__ import annotations

import base64
import http.client
import ipaddress
import math
import os
import re
import socket
import ssl
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import urlsplit

from .strix_broker_models import BrokerHttpRequest, BrokerHttpResponse
from .strix_execution_contract import (
    StrixExecutionContractError,
    authorize_strix_contract_request,
)


class StrixEgressError(RuntimeError):
    pass


class StrixEgressPolicyError(StrixEgressError):
    pass


class StrixEgressNetworkError(StrixEgressError):
    pass


class StrixEgressRateLimitError(StrixEgressPolicyError):
    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = max(0.001, retry_after_seconds)
        super().__init__("Strix egress request rate exceeded")


_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_FORBIDDEN_REQUEST_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_FORBIDDEN_RESPONSE_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_MAX_RATE_KEYS = 4096
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT: OrderedDict[str, float] = OrderedDict()


@dataclass(frozen=True)
class ResolvedEndpoint:
    family: int
    sockaddr: tuple
    address: str
    address_type: str


def _timeout_seconds() -> float:
    raw = os.getenv("XBOW_STRIX_EGRESS_TIMEOUT_SECONDS", "10")
    try:
        value = float(raw)
    except ValueError as exc:
        raise StrixEgressError(
            "XBOW_STRIX_EGRESS_TIMEOUT_SECONDS must be a number"
        ) from exc
    if not math.isfinite(value) or not 1.0 <= value <= 30.0:
        raise StrixEgressError(
            "XBOW_STRIX_EGRESS_TIMEOUT_SECONDS must be between 1 and 30"
        )
    return value


def _max_response_bytes() -> int:
    raw = os.getenv("XBOW_STRIX_EGRESS_MAX_RESPONSE_BYTES", "262144")
    try:
        value = int(raw)
    except ValueError as exc:
        raise StrixEgressError(
            "XBOW_STRIX_EGRESS_MAX_RESPONSE_BYTES must be an integer"
        ) from exc
    if not 1024 <= value <= 1_048_576:
        raise StrixEgressError(
            "XBOW_STRIX_EGRESS_MAX_RESPONSE_BYTES must be between 1 KiB and 1 MiB"
        )
    return value


def _normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    if len(headers) > 32:
        raise StrixEgressPolicyError("too many Strix egress request headers")
    normalized: dict[str, str] = {}
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip()
        value = str(raw_value)
        if (
            not name
            or len(name) > 128
            or not _HEADER_NAME.fullmatch(name)
            or name.lower() in _FORBIDDEN_REQUEST_HEADERS
        ):
            raise StrixEgressPolicyError("unsafe Strix egress request header")
        if len(value.encode("utf-8")) > 4096 or any(
            ord(ch) < 32 and ch != "\t" or ord(ch) == 127
            for ch in value
        ):
            raise StrixEgressPolicyError("unsafe Strix egress request header value")
        normalized[name] = value
    if not any(name.lower() == "user-agent" for name in normalized):
        normalized["User-Agent"] = "xbow-strix-egress/1.0"
    if not any(name.lower() == "accept" for name in normalized):
        normalized["Accept"] = "*/*"
    return normalized


def _public_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise StrixEgressPolicyError("Strix egress resolved an invalid IP address") from exc
    if not address.is_global:
        raise StrixEgressError(
            "Strix egress target resolved to a non-public IP address"
        )
    return address


def resolve_public_endpoint(host: str, port: int) -> ResolvedEndpoint:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        address = _public_ip(str(literal))
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        sockaddr = (
            (str(address), port, 0, 0)
            if family == socket.AF_INET6
            else (str(address), port)
        )
        return ResolvedEndpoint(
            family=family,
            sockaddr=sockaddr,
            address=str(address),
            address_type="ipv6" if address.version == 6 else "ipv4",
        )

    try:
        records = socket.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise StrixEgressNetworkError("Strix egress DNS resolution failed") from exc

    candidates: list[ResolvedEndpoint] = []
    seen: set[tuple[int, str]] = set()
    for family, socktype, _proto, _canonname, sockaddr in records:
        if socktype != socket.SOCK_STREAM or family not in {
            socket.AF_INET,
            socket.AF_INET6,
        }:
            continue
        address_text = str(sockaddr[0])
        address = _public_ip(address_text)
        key = (family, str(address))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            ResolvedEndpoint(
                family=family,
                sockaddr=sockaddr,
                address=str(address),
                address_type="ipv6" if address.version == 6 else "ipv4",
            )
        )

    if not candidates:
        raise StrixEgressNetworkError(\n            "Strix egress DNS resolution returned no usable address"\n        )
    candidates.sort(key=lambda item: (item.address_type, item.address))
    return candidates[0]


def _pinned_create_connection(
    endpoint: ResolvedEndpoint,
    timeout: float,
):
    def create_connection(
        _address,
        timeout_override=socket._GLOBAL_DEFAULT_TIMEOUT,
        source_address=None,
    ):
        actual_timeout = timeout
        if timeout_override is not socket._GLOBAL_DEFAULT_TIMEOUT:
            actual_timeout = float(timeout_override)
        sock = socket.socket(endpoint.family, socket.SOCK_STREAM)
        try:
            sock.settimeout(actual_timeout)
            if source_address is not None:
                sock.bind(source_address)
            sock.connect(endpoint.sockaddr)
            return sock
        except Exception:
            sock.close()
            raise

    return create_connection


def _enforce_rate(contract_hash: str, rps: float) -> None:
    interval = 1.0 / rps
    now = time.monotonic()
    with _RATE_LOCK:
        previous = _LAST_REQUEST_AT.get(contract_hash)
        if previous is not None:
            remaining = interval - (now - previous)
            if remaining > 0:
                raise StrixEgressRateLimitError(remaining)
        _LAST_REQUEST_AT[contract_hash] = now
        _LAST_REQUEST_AT.move_to_end(contract_hash)
        while len(_LAST_REQUEST_AT) > _MAX_RATE_KEYS:
            _LAST_REQUEST_AT.popitem(last=False)


def reset_rate_limits_for_tests() -> None:
    with _RATE_LOCK:
        _LAST_REQUEST_AT.clear()


def _response_headers(response: http.client.HTTPResponse) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    total = 0
    for name, value in response.getheaders():
        if total >= 64:
            break
        clean_name = str(name).strip()
        clean_value = str(value).strip()
        if (
            not clean_name
            or len(clean_name) > 128
            or not _HEADER_NAME.fullmatch(clean_name)
            or clean_name.lower() in _FORBIDDEN_RESPONSE_HEADERS
        ):
            continue
        if len(clean_value.encode("utf-8")) > 4096:
            clean_value = clean_value.encode("utf-8")[:4096].decode(
                "utf-8",
                errors="replace",
            )
        existing = sanitized.get(clean_name)
        sanitized[clean_name] = (
            f"{existing}, {clean_value}" if existing else clean_value
        )
        total += 1
    return sanitized


def perform_bounded_http_request(
    request: BrokerHttpRequest,
    *,
    verification_secret: str,
) -> BrokerHttpResponse:
    try:
        authorized = authorize_strix_contract_request(
            request.contract.to_contract(),
            target=request.target,
            requested_rps=request.requested_rps,
            verification_secret=verification_secret,
        )
    except StrixExecutionContractError as exc:
        raise StrixEgressPolicyError(str(exc)) from exc

    parsed = urlsplit(authorized.target)
    host = authorized.host
    if parsed.scheme not in {"http", "https"}:
        raise StrixEgressPolicyError("Strix egress requires HTTP(S)")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise StrixEgressPolicyError("Strix egress target port is invalid") from exc

    endpoint = resolve_public_endpoint(host, port)
    _enforce_rate(
        authorized.contract_hash,
        authorized.max_requests_per_second,
    )
    timeout = _timeout_seconds()
    headers = _normalize_headers(request.headers)
    target_path = parsed.path or "/"
    if parsed.query:
        target_path += f"?{parsed.query}"

    connection_class = (
        http.client.HTTPSConnection
        if parsed.scheme == "https"
        else http.client.HTTPConnection
    )
    kwargs = {"timeout": timeout}
    if parsed.scheme == "https":
        kwargs["context"] = ssl.create_default_context()
    connection = connection_class(host, port=port, **kwargs)
    connection._create_connection = _pinned_create_connection(
        endpoint,
        timeout,
    )

    max_bytes = _max_response_bytes()
    try:
        connection.request(
            request.method,
            target_path,
            headers=headers,
        )
        response = connection.getresponse()
        body = b""
        truncated = False
        if request.method != "HEAD":
            payload = response.read(max_bytes + 1)
            truncated = len(payload) > max_bytes
            body = payload[:max_bytes]
        return BrokerHttpResponse(
            status_code=int(response.status),
            reason=str(response.reason or "")[:256],
            headers=_response_headers(response),
            body_base64=base64.b64encode(body).decode("ascii"),
            body_bytes=len(body),
            truncated=truncated,
            contract_hash=authorized.contract_hash,
            host=authorized.host,
            method=request.method,
        )
    except (
        OSError,
        TimeoutError,
        http.client.HTTPException,
        ssl.SSLError,
    ) as exc:
        raise StrixEgressNetworkError("Strix egress request failed") from exc
    finally:
        connection.close()
