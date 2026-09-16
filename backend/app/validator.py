from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ValidationPolicyError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class ProbeResult:
    status: str
    url: str
    parameter_names: tuple[str, ...] = ()
    http_status: int | None = None
    content_type: str | None = None
    body_preview: str = ""
    error: str | None = None
    differential: dict[str, object] | None = None

    def json_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class _HttpObservation:
    status: str
    http_status: int | None
    content_type: str | None
    body: bytes
    error: str | None = None


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValidationPolicyError(f"{name} must be a boolean")


def _validation_timeout_seconds() -> float:
    raw = os.getenv("XBOW_VALIDATION_TIMEOUT_SECONDS", "10")
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValidationPolicyError("XBOW_VALIDATION_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(timeout):
        raise ValidationPolicyError("XBOW_VALIDATION_TIMEOUT_SECONDS must be a number")
    if not 1.0 <= timeout <= 30.0:
        raise ValidationPolicyError("XBOW_VALIDATION_TIMEOUT_SECONDS must be between 1 and 30")
    return timeout


def _validation_preview_chars() -> int:
    raw = os.getenv("XBOW_VALIDATION_PREVIEW_CHARS", "4096")
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValidationPolicyError("XBOW_VALIDATION_PREVIEW_CHARS must be an integer") from exc
    if not 0 <= limit <= 16384:
        raise ValidationPolicyError("XBOW_VALIDATION_PREVIEW_CHARS must be between 0 and 16384")
    return limit


def _preview_body(body: bytes, content_type: str | None) -> str:
    if not body:
        return ""
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    text_like = (
        media_type.startswith("text/")
        or media_type in {"application/json", "application/xml", "application/xhtml+xml"}
        or media_type.endswith("+json")
        or media_type.endswith("+xml")
    )
    if not text_like:
        return ""
    return body.decode("utf-8", errors="replace")[:_validation_preview_chars()]


def _redact_query_values(preview: str, url: str) -> str:
    """Remove original query values from persisted evidence previews."""
    if not preview:
        return preview
    values = {
        value
        for _key, value in parse_qsl(urlparse(url).query, keep_blank_values=True)
        if value
    }
    redacted = preview
    candidates: set[str] = set()
    for value in values:
        candidates.add(value)
        candidates.add(quote(value, safe=""))
        candidates.add(quote_plus(value, safe=""))
    for candidate in sorted((item for item in candidates if item), key=len, reverse=True):
        redacted = redacted.replace(candidate, "[redacted]")
    return redacted


def _validation_max_bytes() -> int:
    raw = os.getenv("XBOW_VALIDATION_MAX_BYTES", "262144")
    try:
        max_bytes = int(raw)
    except ValueError as exc:
        raise ValidationPolicyError("XBOW_VALIDATION_MAX_BYTES must be an integer") from exc
    if not 1024 <= max_bytes <= 1_048_576:
        raise ValidationPolicyError("XBOW_VALIDATION_MAX_BYTES must be between 1 KiB and 1 MiB")
    return max_bytes


def _validation_rps(campaign) -> float:
    try:
        rps = float(campaign.target.rules.max_requests_per_second)
    except (TypeError, ValueError) as exc:
        raise ValidationPolicyError("campaign validation rate limit must be a number") from exc
    if not math.isfinite(rps) or rps <= 0:
        raise ValidationPolicyError("campaign validation rate limit must be positive")
    return rps


def _evidence_url(url: str) -> tuple[str, tuple[str, ...]]:
    parsed = urlparse(url)
    parameter_names = tuple(
        sorted({key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)})
    )
    safe_url = parsed._replace(query="", fragment="").geturl()
    return safe_url, parameter_names


def _request_get(opener, url: str, *, timeout: float, max_bytes: int) -> _HttpObservation:
    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": "xbow-perso-independent-validator/1.0",
            "Accept": "*/*",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)[:max_bytes]
            return _HttpObservation(
                status="observed",
                http_status=int(response.status),
                content_type=response.headers.get("Content-Type"),
                body=body,
            )
    except HTTPError as exc:
        body = exc.read(max_bytes + 1)[:max_bytes] if exc.fp else b""
        return _HttpObservation(
            status="observed",
            http_status=int(exc.code),
            content_type=exc.headers.get("Content-Type") if exc.headers else None,
            body=body,
        )
    except (URLError, TimeoutError, OSError) as exc:
        return _HttpObservation(
            status="error",
            http_status=None,
            content_type=None,
            body=b"",
            error=str(exc),
        )


def _differential_marker(campaign, finding, parameter: str) -> str:
    seed = f"{campaign.id}:{finding.id}:{parameter}".encode("utf-8")
    return "xbowv1-" + hashlib.sha256(seed).hexdigest()[:16]


def _marker_url(url: str, campaign, finding) -> tuple[str, str, str] | None:
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not pairs:
        return None
    parameter = pairs[0][0]
    marker = _differential_marker(campaign, finding, parameter)
    pairs[0] = (parameter, marker)
    return parsed._replace(query=urlencode(pairs)).geturl(), parameter, marker


def build_probe_url(campaign, finding) -> str:
    """Resolve one read-only validation URL and fail closed on scope ambiguity."""
    from .main import is_host_allowed

    primary = str(campaign.target.primary_url)
    candidate = finding.endpoint or finding.asset or primary
    if candidate.startswith("/"):
        candidate = urljoin(primary, candidate)
    elif "://" not in candidate:
        # Bare hosts are not sufficient for an HTTP reproduction. Falling back to
        # the campaign primary URL avoids guessing a path or scheme.
        candidate = primary

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValidationPolicyError("validation requires an explicit HTTP(S) URL")
    host = parsed.hostname.lower().rstrip(".")
    rules = campaign.target.rules
    if not is_host_allowed(host, rules.allowed_targets, rules.denied_targets):
        raise ValidationPolicyError("validation URL is outside declared scope")
    if parsed.username or parsed.password:
        raise ValidationPolicyError("userinfo in validation URLs is forbidden")
    return candidate


def safe_http_probe(campaign, finding) -> ProbeResult:
    """Capture bounded HTTP evidence and optionally one inert differential sample.

    Active validation and differential validation are independently gated off by
    default. Redirects are not followed, only GET is used, and a differential
    request may replace only an already-present query value with an inert marker.
    The result is evidence only; it never confirms a vulnerability.
    """
    url = build_probe_url(campaign, finding)
    evidence_url, parameter_names = _evidence_url(url)
    if not _bool_env("XBOW_ENABLE_HTTP_VALIDATION", False):
        return ProbeResult(
            status="dry_run",
            url=evidence_url,
            parameter_names=parameter_names,
        )

    differential_enabled = _bool_env("XBOW_ENABLE_DIFFERENTIAL_VALIDATION", False)
    timeout = _validation_timeout_seconds()
    max_bytes = _validation_max_bytes()
    opener = build_opener(_NoRedirect())
    baseline = _request_get(opener, url, timeout=timeout, max_bytes=max_bytes)
    if baseline.status == "error":
        return ProbeResult(
            status="error",
            url=evidence_url,
            parameter_names=parameter_names,
            error=baseline.error,
        )

    differential: dict[str, object] | None = None
    if differential_enabled:
        marker_request = _marker_url(url, campaign, finding)
        if marker_request is None:
            differential = {
                "eligible": False,
                "reason": "no_existing_query_parameter",
            }
        else:
            marker_url, parameter, marker = marker_request
            time.sleep(1.0 / _validation_rps(campaign))
            marker_observation = _request_get(
                opener,
                marker_url,
                timeout=timeout,
                max_bytes=max_bytes,
            )
            if marker_observation.status == "error":
                differential = {
                    "eligible": True,
                    "parameter": parameter,
                    "reason": "marker_request_error",
                }
            else:
                marker_bytes = marker.encode("utf-8")
                differential = {
                    "eligible": True,
                    "parameter": parameter,
                    "baseline_status": baseline.http_status,
                    "marker_status": marker_observation.http_status,
                    "status_changed": baseline.http_status != marker_observation.http_status,
                    "body_changed": baseline.body != marker_observation.body,
                    "marker_reflected": marker_bytes in marker_observation.body
                    and marker_bytes not in baseline.body,
                }

    preview = _preview_body(baseline.body, baseline.content_type)
    return ProbeResult(
        status="observed",
        url=evidence_url,
        parameter_names=parameter_names,
        http_status=baseline.http_status,
        content_type=baseline.content_type,
        body_preview=_redact_query_values(preview, url),
        differential=differential,
    )
