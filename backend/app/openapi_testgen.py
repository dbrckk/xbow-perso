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
    read_only: bool = True
    execution_mode: str = "preview_only"
    destructive: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        payload["parameters"] = [dict(item) for item in self.parameters]
        payload["response_codes"] = list(self.response_codes)
        payload["response_content_types"] = list(self.response_content_types)
        return payload



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
                )
            )
            if len(cases) > MAX_CASES:
                raise OpenApiPreviewError(f"OpenAPI preview exceeds {MAX_CASES} cases")

    return {
        "schema": "openapi-read-only-preview-v2",
        "source_version": version[:40],
        "execution_mode": "preview_only",
        "read_only": True,
        "network_requests_sent": 0,
        "cases": [case.to_dict() for case in cases],
        "summary": {
            "paths_seen": len(paths),
            "cases_generated": len(cases),
            "mutating_operations_skipped": skipped_mutating,
            "invalid_entries_skipped": skipped_invalid,
        },
    }
