from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any


class OpenApiPreviewError(ValueError):
    pass


READ_ONLY_METHODS = ("get", "head", "options")
MAX_PATHS = 250
MAX_CASES = 500
MAX_PATH_LENGTH = 2048
MAX_OPERATION_ID_LENGTH = 160
MAX_PARAMETER_NAME_LENGTH = 160
MAX_PARAMETER_SCHEMA_TYPE_LENGTH = 80
MAX_RESPONSE_CONTENT_TYPE_LENGTH = 120
MAX_RESPONSE_CODE_LENGTH = 20
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class OpenApiTestCase:
    method: str
    path: str
    operation_id: str | None
    tags: tuple[str, ...]
    authentication_declared: bool
    security_scheme_names: tuple[str, ...]
    security_source: str
    explicitly_public: bool
    parameters: tuple[dict[str, Any], ...]
    response_codes: tuple[str, ...]
    response_content_types: tuple[str, ...]
    risk_signals: tuple[dict[str, Any], ...]
    review_priority: int
    review_priority_reasons: tuple[str, ...]
    read_only: bool = True
    execution_mode: str = "preview_only"
    destructive: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        payload["security_scheme_names"] = list(self.security_scheme_names)
        payload["parameters"] = [dict(item) for item in self.parameters]
        payload["response_codes"] = list(self.response_codes)
        payload["response_content_types"] = list(self.response_content_types)
        payload["risk_signals"] = [dict(item) for item in self.risk_signals]
        payload["review_priority_reasons"] = list(self.review_priority_reasons)
        return payload




RISK_TERMS = {
    "bola_idor": (
        "id", "user_id", "account_id", "order_id", "invoice_id", "tenant_id",
        "customer_id", "project_id", "document_id", "resource_id",
    ),
    "ssrf": (
        "url", "uri", "callback", "callback_url", "webhook", "redirect", "return_url",
        "target", "destination", "endpoint", "host",
    ),
    "auth_session": (
        "token", "jwt", "oauth", "authorization", "session", "refresh_token",
        "access_token",
    ),
    "sensitive_data": (
        "email", "phone", "address", "ssn", "tax", "payment", "card", "bank",
        "secret", "credential", "api_key",
    ),
}


def _operation_tags(operation: dict[str, Any]) -> tuple[str, ...]:
    raw_tags = operation.get("tags")
    if not isinstance(raw_tags, list):
        return ()
    return tuple(
        str(tag).strip()[:80]
        for tag in raw_tags
        if isinstance(tag, str) and tag.strip()
    )[:20]


def _signal_identifiers(value: str) -> tuple[set[str], set[str]]:
    raw = str(value or "").strip()
    if not raw:
        return set(), set()
    camel_split = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", camel_split).strip("_").lower()
    if not normalized:
        return set(), set()

    identifiers = {part for part in normalized.split("__") if part}
    identifiers.add(normalized)
    tokens = {token for token in normalized.split("_") if token}
    return identifiers, tokens


def _operation_signal_vocabulary(
    path: str,
    operation: dict[str, Any],
    parameters: tuple[dict[str, Any], ...],
) -> tuple[set[str], set[str]]:
    values = [path, str(operation.get("operationId") or "")]
    values.extend(_operation_tags(operation))
    values.extend(str(item.get("name") or "") for item in parameters)

    identifiers: set[str] = set()
    tokens: set[str] = set()
    for value in values:
        value_identifiers, value_tokens = _signal_identifiers(value)
        identifiers.update(value_identifiers)
        tokens.update(value_tokens)
    return identifiers, tokens


def _matched_risk_terms(
    category: str,
    identifiers: set[str],
    tokens: set[str],
) -> list[str]:
    matches: list[str] = []
    for term in RISK_TERMS[category]:
        normalized = term.lower()
        if "_" in normalized:
            if normalized in identifiers:
                matches.append(term)
            continue
        if normalized in tokens or normalized in identifiers:
            matches.append(term)
    return sorted(set(matches))


def _risk_signal(
    *,
    category: str,
    confidence: str,
    reason: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "category": category,
        "confidence": confidence,
        "reason": reason,
        "evidence": evidence[:12],
        "advisory": True,
        "vulnerability_confirmed": False,
    }


def _operation_risk_signals(
    path: str,
    operation: dict[str, Any],
    parameters: tuple[dict[str, Any], ...],
    *,
    authentication_declared: bool,
) -> list[dict[str, Any]]:
    identifiers, tokens = _operation_signal_vocabulary(path, operation, parameters)
    signals: list[dict[str, Any]] = []

    object_refs = _matched_risk_terms("bola_idor", identifiers, tokens)
    if object_refs:
        signals.append(
            _risk_signal(
                category="bola_idor_review",
                confidence="medium",
                reason="Object identifiers are declared in a read-only operation and may warrant authorization-boundary review.",
                evidence=object_refs,
            )
        )

    ssrf_refs = _matched_risk_terms("ssrf", identifiers, tokens)
    if ssrf_refs:
        signals.append(
            _risk_signal(
                category="ssrf_input_review",
                confidence="medium",
                reason="URL/host-like inputs are declared and may warrant server-side request handling review.",
                evidence=ssrf_refs,
            )
        )

    auth_refs = _matched_risk_terms("auth_session", identifiers, tokens)
    if auth_refs or authentication_declared:
        signals.append(
            _risk_signal(
                category="auth_session_review",
                confidence="low" if authentication_declared and not auth_refs else "medium",
                reason="Authentication/session semantics are present and may warrant JWT/OAuth/session handling review.",
                evidence=(["security_declared"] if authentication_declared else []) + auth_refs,
            )
        )

    sensitive_refs = _matched_risk_terms("sensitive_data", identifiers, tokens)
    if sensitive_refs:
        signals.append(
            _risk_signal(
                category="sensitive_data_review",
                confidence="medium",
                reason="Potentially sensitive data fields are referenced and may warrant exposure/minimization review.",
                evidence=sensitive_refs,
            )
        )

    return signals


RISK_REVIEW_WEIGHTS = {
    "bola_idor_review": 30,
    "ssrf_input_review": 30,
    "auth_session_review": 20,
    "sensitive_data_review": 20,
}
CONFIDENCE_WEIGHTS = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.25,
}


def _review_priority(
    risk_signals: list[dict[str, Any]],
    *,
    authentication_declared: bool,
    parameter_count: int,
) -> tuple[int, tuple[str, ...]]:
    score = 0.0
    reasons: list[str] = []

    for signal in risk_signals:
        category = str(signal.get("category") or "")
        confidence = str(signal.get("confidence") or "low")
        weight = RISK_REVIEW_WEIGHTS.get(category, 0)
        factor = CONFIDENCE_WEIGHTS.get(confidence, 0.5)
        if weight:
            score += weight * factor
            reasons.append(category)

    if authentication_declared and risk_signals:
        score += 5
        reasons.append("authenticated_surface")
    if parameter_count >= 3:
        score += 5
        reasons.append("parameter_rich_surface")

    bounded = max(0, min(100, int(round(score))))
    return bounded, tuple(dict.fromkeys(reasons))[:12]


def _review_summary(cases: list[OpenApiTestCase]) -> dict[str, Any]:
    category_counts: dict[str, int] = {}
    flagged_operations = 0
    for case in cases:
        if case.risk_signals:
            flagged_operations += 1
        for signal in case.risk_signals:
            category = str(signal.get("category") or "").strip()
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1

    ranked = sorted(
        cases,
        key=lambda item: (-item.review_priority, item.path, item.method),
    )
    top = [
        {
            "method": case.method,
            "path": case.path,
            "operation_id": case.operation_id,
            "review_priority": case.review_priority,
            "review_priority_reasons": list(case.review_priority_reasons),
        }
        for case in ranked[:10]
        if case.review_priority > 0
    ]
    return {
        "advisory": True,
        "vulnerabilities_confirmed": 0,
        "flagged_operations": flagged_operations,
        "unflagged_operations": max(0, len(cases) - flagged_operations),
        "max_review_priority": max((case.review_priority for case in cases), default=0),
        "category_counts": dict(sorted(category_counts.items())),
        "top_review_operations": top,
    }



MAX_SECURITY_SCHEMES = 100
MAX_SECURITY_REFERENCES = 100


def _security_requirement_names(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        for raw_name in item:
            name = str(raw_name).strip()[:160]
            if name:
                names.add(name)
            if len(names) >= MAX_SECURITY_REFERENCES:
                break
        if len(names) >= MAX_SECURITY_REFERENCES:
            break
    return tuple(sorted(names))


def _security_scheme_inventory(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    source: Any = None
    components = document.get("components")
    if isinstance(components, dict):
        source = components.get("securitySchemes")
    if not isinstance(source, dict):
        source = document.get("securityDefinitions")
    if not isinstance(source, dict):
        return ()

    inventory: list[dict[str, Any]] = []
    for raw_name, raw_scheme in sorted(source.items(), key=lambda item: str(item[0])):
        if len(inventory) >= MAX_SECURITY_SCHEMES:
            break
        if not isinstance(raw_scheme, dict) or "$ref" in raw_scheme:
            continue
        name = str(raw_name).strip()[:160]
        if not name:
            continue
        scheme_type = str(raw_scheme.get("type") or "").strip().lower()[:80] or None
        http_scheme = str(raw_scheme.get("scheme") or "").strip().lower()[:80] or None
        bearer_format = str(raw_scheme.get("bearerFormat") or "").strip()[:80] or None
        location = str(raw_scheme.get("in") or "").strip().lower()[:40] or None

        flows: list[str] = []
        raw_flows = raw_scheme.get("flows")
        if isinstance(raw_flows, dict):
            flows = sorted(
                str(flow).strip()[:80]
                for flow, value in raw_flows.items()
                if isinstance(flow, str) and flow.strip() and isinstance(value, dict)
            )[:20]
        swagger_flow = str(raw_scheme.get("flow") or "").strip()[:80]
        if swagger_flow and swagger_flow not in flows:
            flows.append(swagger_flow)

        inventory.append(
            {
                "name": name,
                "type": scheme_type,
                "scheme": http_scheme,
                "bearer_format": bearer_format,
                "in": location,
                "oauth_flows": flows[:20],
                "open_id_connect": bool(str(raw_scheme.get("openIdConnectUrl") or "").strip()),
            }
        )
    return tuple(inventory)


def _authentication_summary(
    document: dict[str, Any],
    cases: list[OpenApiTestCase],
) -> dict[str, Any]:
    inventory = _security_scheme_inventory(document)
    defined = {str(item.get("name") or "") for item in inventory}
    referenced = sorted({
        name
        for case in cases
        for name in case.security_scheme_names
        if name
    })
    unknown = sorted(name for name in referenced if name not in defined)

    explicit_public = [
        {"method": case.method, "path": case.path}
        for case in cases
        if case.explicitly_public
    ][:50]

    sensitive_unauthenticated = [
        {"method": case.method, "path": case.path}
        for case in cases
        if not case.authentication_declared
        and any(
            str(signal.get("category") or "") in {
                "bola_idor_review",
                "sensitive_data_review",
                "auth_session_review",
            }
            for signal in case.risk_signals
        )
    ][:50]

    return {
        "advisory": True,
        "security_schemes": [dict(item) for item in inventory],
        "defined_scheme_count": len(inventory),
        "referenced_scheme_names": referenced[:MAX_SECURITY_REFERENCES],
        "unknown_scheme_references": unknown[:MAX_SECURITY_REFERENCES],
        "explicit_public_overrides": explicit_public,
        "sensitive_unauthenticated_operations": sensitive_unauthenticated,
        "vulnerabilities_confirmed": 0,
    }


def _normalized_parameters(path_item: dict[str, Any], operation: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    combined: list[Any] = []
    for source in (path_item.get("parameters"), operation.get("parameters")):
        if isinstance(source, list):
            combined.extend(source)

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in combined:
        if not isinstance(item, dict) or "$ref" in item:
            continue
        name = str(item.get("name") or "").strip()
        location = str(item.get("in") or "").strip().lower()
        if not name or location not in {"path", "query", "header", "cookie"}:
            continue
        if len(name) > MAX_PARAMETER_NAME_LENGTH:
            raise OpenApiPreviewError(
                f"OpenAPI parameter name exceeds {MAX_PARAMETER_NAME_LENGTH} characters"
            )
        key = (location, name.lower())
        if key in seen:
            continue
        seen.add(key)
        schema = item.get("schema") if isinstance(item.get("schema"), dict) else {}
        schema_type = str(schema.get("type") or "").strip()
        if len(schema_type) > MAX_PARAMETER_SCHEMA_TYPE_LENGTH:
            raise OpenApiPreviewError(
                "OpenAPI parameter schema type exceeds "
                f"{MAX_PARAMETER_SCHEMA_TYPE_LENGTH} characters"
            )
        normalized.append(
            {
                "name": name,
                "in": location,
                "required": bool(item.get("required")) or location == "path",
                "schema_type": schema_type or None,
            }
        )
        if len(normalized) >= 100:
            break
    return tuple(normalized)


def _response_metadata(operation: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return (), ()

    codes: list[str] = []
    content_types: set[str] = set()
    for raw_code, response in sorted(responses.items(), key=lambda item: str(item[0])):
        code = str(raw_code).strip()
        if len(code) > MAX_RESPONSE_CODE_LENGTH:
            raise OpenApiPreviewError(
                f"OpenAPI response code exceeds {MAX_RESPONSE_CODE_LENGTH} characters"
            )
        codes.append(code)
        if isinstance(response, dict):
            content = response.get("content")
            if isinstance(content, dict):
                for media_type in content:
                    if isinstance(media_type, str) and media_type.strip():
                        normalized_media_type = media_type.strip()
                        if len(normalized_media_type) > MAX_RESPONSE_CONTENT_TYPE_LENGTH:
                            raise OpenApiPreviewError(
                                "OpenAPI response content type exceeds "
                                f"{MAX_RESPONSE_CONTENT_TYPE_LENGTH} characters"
                            )
                        content_types.add(normalized_media_type)
        if len(codes) >= 50:
            break
    return tuple(codes), tuple(sorted(content_types)[:50])

def _document_size_bytes(document: dict[str, Any]) -> int:
    try:
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OpenApiPreviewError("OpenAPI document must be JSON-serializable") from exc
    return len(encoded)


def build_openapi_read_only_preview(document: dict[str, Any]) -> dict[str, Any]:
    """Generate bounded, non-executing test cases from an OpenAPI document.

    Only GET/HEAD/OPTIONS operations are included. The preview never sends
    requests, invents payloads, follows external references, or enables a
    scanner. It is intended as an advisory input to the existing scope-aware
    orchestration pipeline.
    """

    if not isinstance(document, dict):
        raise OpenApiPreviewError("OpenAPI document must be an object")
    if _document_size_bytes(document) > MAX_DOCUMENT_BYTES:
        raise OpenApiPreviewError(
            f"OpenAPI document exceeds {MAX_DOCUMENT_BYTES} bytes"
        )

    version = str(document.get("openapi") or document.get("swagger") or "").strip()
    if not version:
        raise OpenApiPreviewError("OpenAPI/Swagger version is required")

    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise OpenApiPreviewError("OpenAPI paths must be an object")
    if len(paths) > MAX_PATHS:
        raise OpenApiPreviewError(f"OpenAPI document exceeds {MAX_PATHS} paths")

    cases: list[OpenApiTestCase] = []
    skipped_mutating = 0
    skipped_invalid = 0

    for raw_path, raw_item in sorted(paths.items(), key=lambda item: str(item[0])):
        path = str(raw_path)
        if not path.startswith("/") or not isinstance(raw_item, dict):
            skipped_invalid += 1
            continue
        if len(path) > MAX_PATH_LENGTH:
            raise OpenApiPreviewError(
                f"OpenAPI path exceeds {MAX_PATH_LENGTH} characters"
            )

        for method, operation in raw_item.items():
            normalized = str(method).lower()
            if normalized.startswith("x-") or normalized in {"parameters", "summary", "description", "$ref"}:
                continue
            if normalized not in READ_ONLY_METHODS:
                if normalized in {"post", "put", "patch", "delete", "trace"}:
                    skipped_mutating += 1
                continue
            if not isinstance(operation, dict):
                skipped_invalid += 1
                continue

            tags = _operation_tags(operation)
            raw_operation_id = operation.get("operationId")
            operation_id = None
            if raw_operation_id is not None:
                operation_id = str(raw_operation_id).strip()
                if not operation_id:
                    operation_id = None
                elif len(operation_id) > MAX_OPERATION_ID_LENGTH:
                    raise OpenApiPreviewError(
                        f"OpenAPI operationId exceeds {MAX_OPERATION_ID_LENGTH} characters"
                    )

            operation_has_security = "security" in operation
            security = operation.get("security") if operation_has_security else document.get("security")
            authentication_declared = bool(security)
            security_scheme_names = _security_requirement_names(security)
            security_source = (
                "operation"
                if operation_has_security
                else ("document" if "security" in document else "none")
            )
            explicitly_public = operation_has_security and operation.get("security") == []
            parameters = _normalized_parameters(raw_item, operation)
            response_codes, response_content_types = _response_metadata(operation)
            risk_signals = _operation_risk_signals(
                path,
                operation,
                parameters,
                authentication_declared=authentication_declared,
            )
            review_priority, review_priority_reasons = _review_priority(
                risk_signals,
                authentication_declared=authentication_declared,
                parameter_count=len(parameters),
            )

            cases.append(
                OpenApiTestCase(
                    method=normalized.upper(),
                    path=path,
                    operation_id=operation_id,
                    tags=tags,
                    authentication_declared=authentication_declared,
                    security_scheme_names=security_scheme_names,
                    security_source=security_source,
                    explicitly_public=explicitly_public,
                    parameters=parameters,
                    response_codes=response_codes,
                    response_content_types=response_content_types,
                    risk_signals=tuple(risk_signals),
                    review_priority=review_priority,
                    review_priority_reasons=review_priority_reasons,
                )
            )
            if len(cases) > MAX_CASES:
                raise OpenApiPreviewError(f"OpenAPI preview exceeds {MAX_CASES} cases")

    return {
        "schema": "openapi-read-only-preview-v6",
        "source_version": version[:40],
        "execution_mode": "preview_only",
        "read_only": True,
        "network_requests_sent": 0,
        "cases": [
            case.to_dict()
            for case in sorted(
                cases,
                key=lambda item: (-item.review_priority, item.path, item.method),
            )
        ],
        "summary": {
            "paths_seen": len(paths),
            "cases_generated": len(cases),
            "mutating_operations_skipped": skipped_mutating,
            "invalid_entries_skipped": skipped_invalid,
            "review": _review_summary(cases),
            "authentication": _authentication_summary(document, cases),
        },
    }
