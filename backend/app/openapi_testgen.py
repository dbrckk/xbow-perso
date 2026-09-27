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
    read_only: bool = True
    execution_mode: str = "preview_only"
    destructive: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        return payload


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

            cases.append(
                OpenApiTestCase(
                    method=normalized.upper(),
                    path=path[:2048],
                    operation_id=operation_id,
                    tags=tags,
                    authentication_declared=authentication_declared,
                )
            )
            if len(cases) > MAX_CASES:
                raise OpenApiPreviewError(f"OpenAPI preview exceeds {MAX_CASES} cases")

    return {
        "schema": "openapi-read-only-preview-v1",
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
