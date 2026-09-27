from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class OpenApiPreviewError(ValueError):
    pass


READ_ONLY_METHODS = ("get", "head", "options")
MAX_PATHS = 250
MAX_CASES = 500


@dataclass(frozen=True)
class OpenApiTestCase:
    method: str
    path: str
    operation_id: str | None
    tags: tuple[str, ...]
    authentication_declared: bool
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
        "url", "uri", "callback", "webhook", "redirect", "return_url", "target",
        "destination", "endpoint", "host",
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
    haystack_parts = [path.lower(), str(operation.get("operationId") or "").lower()]
    haystack_parts.extend(str(tag).lower() for tag in operation.get("tags", []) if isinstance(tag, str))
    haystack_parts.extend(str(item.get("name") or "").lower() for item in parameters)
    haystack = " ".join(haystack_parts)

    signals: list[dict[str, Any]] = []

    object_refs = sorted({
        term for term in RISK_TERMS["bola_idor"]
        if term in haystack
    })
    if object_refs:
        signals.append(
            _risk_signal(
                category="bola_idor_review",
                confidence="medium",
                reason="Object identifiers are declared in a read-only operation and may warrant authorization-boundary review.",
                evidence=object_refs,
            )
        )

    ssrf_refs = sorted({
        term for term in RISK_TERMS["ssrf"]
        if term in haystack
    })
    if ssrf_refs:
        signals.append(
            _risk_signal(
                category="ssrf_input_review",
                confidence="medium",
                reason="URL/host-like inputs are declared and may warrant server-side request handling review.",
                evidence=ssrf_refs,
            )
        )

    auth_refs = sorted({
        term for term in RISK_TERMS["auth_session"]
        if term in haystack
    })
    if auth_refs or authentication_declared:
        signals.append(
            _risk_signal(
                category="auth_session_review",
                confidence="low" if authentication_declared and not auth_refs else "medium",
                reason="Authentication/session semantics are present and may warrant JWT/OAuth/session handling review.",
                evidence=(["security_declared"] if authentication_declared else []) + auth_refs,
            )
        )

    sensitive_refs = sorted({
        term for term in RISK_TERMS["sensitive_data"]
        if term in haystack
    })
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
        name = str(item.get("name") or "").strip()[:160]
        location = str(item.get("in") or "").strip().lower()
        if not name or location not in {"path", "query", "header", "cookie"}:
            continue
        key = (location, name.lower())
        if key in seen:
            continue
        seen.add(key)
        schema = item.get("schema") if isinstance(item.get("schema"), dict) else {}
        normalized.append(
            {
                "name": name,
                "in": location,
                "required": bool(item.get("required")) or location == "path",
                "schema_type": str(schema.get("type") or "")[:80] or None,
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
        code = str(raw_code)[:20]
        codes.append(code)
        if isinstance(response, dict):
            content = response.get("content")
            if isinstance(content, dict):
                for media_type in content:
                    if isinstance(media_type, str) and media_type.strip():
                        content_types.add(media_type.strip()[:120])
        if len(codes) >= 50:
            break
    return tuple(codes), tuple(sorted(content_types)[:50])

def build_openapi_read_only_preview(document: dict[str, Any]) -> dict[str, Any]:
    """Generate bounded, non-executing test cases from an OpenAPI document.

    Only GET/HEAD/OPTIONS operations are included. The preview never sends
    requests, invents payloads, follows external references, or enables a
    scanner. It is intended as an advisory input to the existing scope-aware
    orchestration pipeline.
    """

    if not isinstance(document, dict):
        raise OpenApiPreviewError("OpenAPI document must be an object")

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

            tags = tuple(
                str(tag)[:80]
                for tag in operation.get("tags", [])
                if isinstance(tag, str) and tag.strip()
            )[:20]
            operation_id = operation.get("operationId")
            if operation_id is not None:
                operation_id = str(operation_id)[:160]

            security = operation.get("security", document.get("security"))
            authentication_declared = bool(security)
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
                    path=path[:2048],
                    operation_id=operation_id,
                    tags=tags,
                    authentication_declared=authentication_declared,
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
        "schema": "openapi-read-only-preview-v5",
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
        },
    }
