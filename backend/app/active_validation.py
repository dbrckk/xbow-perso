from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse


SAFE_PROBE_PLAN_SCHEMA = "safe-probe-plan-v1"
_RESERVED_ORIGIN = "https://xbow.invalid"
_RESERVED_REDIRECT = "https://xbow.invalid/redirect-check"
_REDIRECT_PARAMETER_NAMES = frozenset(
    {
        "continue",
        "destination",
        "next",
        "redirect",
        "redirect_uri",
        "return",
        "return_url",
        "target",
        "url",
    }
)
_HARD_MAX_PARAMETERS = 10
_HARD_MAX_REQUESTS = 16


class ActiveValidationPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class SafeProbe:
    kind: str
    method: str
    request_url: str
    headers: tuple[tuple[str, str], ...] = ()
    parameter: str | None = None
    marker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        parsed = urlparse(self.request_url)
        payload = asdict(self)
        payload["request_url"] = parsed._replace(query="", fragment="").geturl()
        payload["headers"] = [
            {"name": name, "value": value}
            for name, value in self.headers
        ]
        return payload


@dataclass(frozen=True)
class SafeProbePlan:
    schema: str
    finding_id: str
    target_url: str
    parameter_names: tuple[str, ...]
    probes: tuple[SafeProbe, ...]
    max_requests: int
    max_parameters: int
    skipped_probe_count: int
    enabled: bool
    automatic_execution_authorized: bool
    non_destructive_only: bool
    redirects_followed: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["parameter_names"] = list(self.parameter_names)
        payload["probes"] = [probe.to_dict() for probe in self.probes]
        return payload


def _validate_target_url(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ActiveValidationPlanError("validation target URL is required")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ActiveValidationPlanError(
            "validation target must be an explicit HTTP(S) URL"
        )
    if parsed.username or parsed.password:
        raise ActiveValidationPlanError(
            "validation target userinfo is forbidden"
        )
    return parsed._replace(fragment="").geturl()


def _bounded_int(value: int, *, name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ActiveValidationPlanError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ActiveValidationPlanError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _parameter_names(url: str) -> tuple[str, ...]:
    parsed = urlparse(url)
    seen: set[str] = set()
    names: list[str] = []
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(key)
    return tuple(names)


def _marker(finding_id: str, parameter: str) -> str:
    digest = hashlib.sha256(
        f"{finding_id}:{parameter}".encode("utf-8")
    ).hexdigest()[:16]
    return f"xbowv2-{digest}"


def _replace_first_parameter(url: str, parameter: str, value: str) -> str:
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    replaced = False
    updated: list[tuple[str, str]] = []
    for key, current in pairs:
        if not replaced and key == parameter:
            updated.append((key, value))
            replaced = True
        else:
            updated.append((key, current))
    if not replaced:
        raise ActiveValidationPlanError(
            "probe parameter is not present in target URL"
        )
    return parsed._replace(query=urlencode(updated), fragment="").geturl()


def build_safe_probe_plan(
    *,
    finding_id: str,
    target_url: str,
    enabled: bool = False,
    parameter_validation_enabled: bool = False,
    cors_validation_enabled: bool = False,
    redirect_validation_enabled: bool = False,
    max_parameters: int = 5,
    max_requests: int = 8,
) -> SafeProbePlan:
    """Build bounded inert GET probes without performing network I/O.

    The plan never authorizes execution. A future executor must independently
    re-check scope, feature gates, request budgets and rate limits immediately
    before each request.
    """

    if not isinstance(finding_id, str) or not finding_id.strip():
        raise ActiveValidationPlanError("finding id is required")
    target = _validate_target_url(target_url)
    max_parameters = _bounded_int(
        max_parameters,
        name="max_parameters",
        minimum=0,
        maximum=_HARD_MAX_PARAMETERS,
    )
    max_requests = _bounded_int(
        max_requests,
        name="max_requests",
        minimum=1,
        maximum=_HARD_MAX_REQUESTS,
    )
    names = _parameter_names(target)
    safe_target = urlparse(target)._replace(query="", fragment="").geturl()

    if not enabled:
        return SafeProbePlan(
            schema=SAFE_PROBE_PLAN_SCHEMA,
            finding_id=finding_id,
            target_url=safe_target,
            parameter_names=names,
            probes=(),
            max_requests=max_requests,
            max_parameters=max_parameters,
            skipped_probe_count=0,
            enabled=False,
            automatic_execution_authorized=False,
            non_destructive_only=True,
            redirects_followed=False,
        )

    candidates: list[SafeProbe] = [
        SafeProbe(
            kind="baseline",
            method="GET",
            request_url=target,
        )
    ]

    selected_names = names[:max_parameters]
    if parameter_validation_enabled:
        for parameter in selected_names:
            marker = _marker(finding_id, parameter)
            candidates.append(
                SafeProbe(
                    kind="parameter_differential",
                    method="GET",
                    request_url=_replace_first_parameter(
                        target,
                        parameter,
                        marker,
                    ),
                    parameter=parameter,
                    marker=marker,
                )
            )

    if cors_validation_enabled:
        candidates.append(
            SafeProbe(
                kind="cors_origin",
                method="GET",
                request_url=target,
                headers=(("Origin", _RESERVED_ORIGIN),),
            )
        )

    if redirect_validation_enabled:
        for parameter in selected_names:
            if parameter.lower() not in _REDIRECT_PARAMETER_NAMES:
                continue
            candidates.append(
                SafeProbe(
                    kind="redirect_location",
                    method="GET",
                    request_url=_replace_first_parameter(
                        target,
                        parameter,
                        _RESERVED_REDIRECT,
                    ),
                    parameter=parameter,
                    marker=_RESERVED_REDIRECT,
                )
            )

    probes = tuple(candidates[:max_requests])
    skipped = max(0, len(candidates) - len(probes))
    return SafeProbePlan(
        schema=SAFE_PROBE_PLAN_SCHEMA,
        finding_id=finding_id,
        target_url=safe_target,
        parameter_names=names,
        probes=probes,
        max_requests=max_requests,
        max_parameters=max_parameters,
        skipped_probe_count=skipped,
        enabled=True,
        automatic_execution_authorized=False,
        non_destructive_only=True,
        redirects_followed=False,
    )



@dataclass(frozen=True)
class ValidationSignal:
    kind: str
    strength: str
    reason: str
    parameter: str | None = None
    evidence: dict[str, Any] | None = None
    exploitability_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_cors_response(
    headers: Mapping[str, object],
    *,
    parameter: str | None = None,
) -> ValidationSignal:
    normalized = {
        str(name).strip().lower(): str(value).strip()
        for name, value in headers.items()
    }
    allow_origin = normalized.get("access-control-allow-origin", "")
    allow_credentials = (
        normalized.get("access-control-allow-credentials", "").lower()
        == "true"
    )
    vary_tokens = {
        item.strip().lower()
        for item in normalized.get("vary", "").split(",")
        if item.strip()
    }

    evidence = {
        "allow_origin": allow_origin,
        "allow_credentials": allow_credentials,
        "vary_origin": "origin" in vary_tokens,
        "synthetic_origin": _RESERVED_ORIGIN,
    }
    if allow_origin == _RESERVED_ORIGIN and allow_credentials:
        return ValidationSignal(
            kind="cors",
            strength="strong",
            reason="synthetic_origin_reflected_with_credentials",
            parameter=parameter,
            evidence=evidence,
        )
    if allow_origin == _RESERVED_ORIGIN:
        return ValidationSignal(
            kind="cors",
            strength="weak",
            reason="synthetic_origin_reflected",
            parameter=parameter,
            evidence=evidence,
        )
    if allow_origin == "*":
        return ValidationSignal(
            kind="cors",
            strength="weak",
            reason="wildcard_origin_observed",
            parameter=parameter,
            evidence=evidence,
        )
    return ValidationSignal(
        kind="cors",
        strength="none",
        reason="no_cors_signal",
        parameter=parameter,
        evidence=evidence,
    )


def analyze_redirect_response(
    *,
    http_status: int | None,
    location: str | None,
    parameter: str | None = None,
) -> ValidationSignal:
    evidence: dict[str, Any] = {
        "http_status": http_status,
        "location_exact_reserved_match": False,
    }
    if (
        not isinstance(http_status, int)
        or isinstance(http_status, bool)
        or not 300 <= http_status <= 399
        or not isinstance(location, str)
        or not location.strip()
    ):
        return ValidationSignal(
            kind="redirect",
            strength="none",
            reason="not_exact_reserved_redirect",
            parameter=parameter,
            evidence=evidence,
        )

    parsed = urlparse(location.strip())
    exact = (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() == "xbow.invalid"
        and parsed.port is None
        and parsed.path == "/redirect-check"
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
        and not parsed.username
        and not parsed.password
    )
    evidence["location_exact_reserved_match"] = exact
    if exact:
        return ValidationSignal(
            kind="redirect",
            strength="strong",
            reason="exact_reserved_destination_returned",
            parameter=parameter,
            evidence=evidence,
        )
    return ValidationSignal(
        kind="redirect",
        strength="none",
        reason="not_exact_reserved_redirect",
        parameter=parameter,
        evidence=evidence,
    )
