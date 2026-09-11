from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlparse
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

    def json_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False).encode("utf-8")


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
    if not 1.0 <= timeout <= 30.0:
        raise ValidationPolicyError("XBOW_VALIDATION_TIMEOUT_SECONDS must be between 1 and 30")
    return timeout


def _validation_max_bytes() -> int:
    raw = os.getenv("XBOW_VALIDATION_MAX_BYTES", "262144")
    try:
        max_bytes = int(raw)
    except ValueError as exc:
        raise ValidationPolicyError("XBOW_VALIDATION_MAX_BYTES must be an integer") from exc
    if not 1024 <= max_bytes <= 1_048_576:
        raise ValidationPolicyError("XBOW_VALIDATION_MAX_BYTES must be between 1 KiB and 1 MiB")
    return max_bytes


def _evidence_url(url: str) -> tuple[str, tuple[str, ...]]:
    parsed = urlparse(url)
    parameter_names = tuple(
        sorted({key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)})
    )
    safe_url = parsed._replace(query="", fragment="").geturl()
    return safe_url, parameter_names


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
    """Perform one bounded, non-destructive GET for independent evidence capture.

    Active validation is off by default. Redirects are deliberately not followed,
    credentials are never injected, and the response body is truncated. This probe
    observes a target; it never decides that a vulnerability is confirmed.
    """
    url = build_probe_url(campaign, finding)
    evidence_url, parameter_names = _evidence_url(url)
    if not _bool_env("XBOW_ENABLE_HTTP_VALIDATION", False):
        return ProbeResult(
            status="dry_run",
            url=evidence_url,
            parameter_names=parameter_names,
        )

    timeout = _validation_timeout_seconds()
    max_bytes = _validation_max_bytes()
    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": "xbow-perso-independent-validator/1.0",
            "Accept": "*/*",
            "Cache-Control": "no-cache",
        },
    )
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)[:max_bytes]
            return ProbeResult(
                status="observed",
                url=evidence_url,
                parameter_names=parameter_names,
                http_status=int(response.status),
                content_type=response.headers.get("Content-Type"),
                body_preview=body.decode("utf-8", errors="replace"),
            )
    except HTTPError as exc:
        # Redirects and non-2xx responses are observations, not execution failures.
        body = exc.read(max_bytes + 1)[:max_bytes] if exc.fp else b""
        return ProbeResult(
            status="observed",
            url=evidence_url,
            parameter_names=parameter_names,
            http_status=int(exc.code),
            content_type=exc.headers.get("Content-Type") if exc.headers else None,
            body_preview=body.decode("utf-8", errors="replace"),
        )
    except (URLError, TimeoutError, OSError) as exc:
        return ProbeResult(
            status="error",
            url=evidence_url,
            parameter_names=parameter_names,
            error=str(exc),
        )
