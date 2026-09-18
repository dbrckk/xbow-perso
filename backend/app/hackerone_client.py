from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .hackerone_scope_import import HackerOneScopeImportError, import_hackerone_structured_scope
from .secret_vault import SecretVaultError, resolve_secret


_API_ROOT = "https://api.hackerone.com/v1/"
_PAGE_SIZE = 100
_MAX_PAGES = 100


class HackerOneClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HackerOneClientError("HackerOne transport refused HTTP redirect")


@dataclass(frozen=True)
class HackerOneCredentials:
    username: str
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "username", _validate_credential(self.username, "username", 1, 512))
        object.__setattr__(self, "token", _validate_credential(self.token, "token", 16, 4096))

    def headers(self) -> dict[str, str]:
        raw = f"{self.username}:{self.token}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "User-Agent": "xbow-perso/hackerone-readonly",
        }


def _validate_credential(value: str | None, label: str, minimum: int, maximum: int) -> str:
    if value is None:
        raise HackerOneClientError("HackerOne credentials are not configured")
    if not isinstance(value, str):
        raise HackerOneClientError(f"HackerOne API {label} is invalid")
    if value != value.strip():
        raise HackerOneClientError(f"HackerOne API {label} must not contain surrounding whitespace")
    encoded = value.encode("utf-8")
    if not minimum <= len(encoded) <= maximum:
        raise HackerOneClientError(f"HackerOne API {label} length is invalid")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise HackerOneClientError(f"HackerOne API {label} contains control characters")
    return value


def load_hackerone_credentials() -> HackerOneCredentials:
    try:
        username = resolve_secret("hackerone_api_username", "XBOW_HACKERONE_API_USERNAME")
        token = resolve_secret("hackerone_api_token", "XBOW_HACKERONE_API_TOKEN")
    except SecretVaultError as exc:
        raise HackerOneClientError("HackerOne credentials are unavailable") from exc
    return HackerOneCredentials(username=username, token=token)


def _timeout_seconds() -> float:
    raw = (os.getenv("XBOW_HACKERONE_TIMEOUT_SECONDS") or "10").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise HackerOneClientError("XBOW_HACKERONE_TIMEOUT_SECONDS must be numeric") from exc
    if not 1.0 <= value <= 60.0:
        raise HackerOneClientError("HackerOne timeout must be between 1 and 60 seconds")
    return value


def _max_response_bytes() -> int:
    raw = (os.getenv("XBOW_HACKERONE_MAX_RESPONSE_BYTES") or str(2 * 1024 * 1024)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise HackerOneClientError("XBOW_HACKERONE_MAX_RESPONSE_BYTES must be an integer") from exc
    if not 1024 <= value <= 8 * 1024 * 1024:
        raise HackerOneClientError("HackerOne response limit must be between 1 KiB and 8 MiB")
    return value


def _validate_path(path: str) -> str:
    if not isinstance(path, str):
        raise HackerOneClientError("HackerOne API path is invalid")
    value = path.strip()
    if value != path or not value:
        raise HackerOneClientError("HackerOne API path is invalid")
    if value.startswith(("/", "//")) or "://" in value or "?" in value or "#" in value:
        raise HackerOneClientError("HackerOne API path must be relative to the fixed origin")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise HackerOneClientError("HackerOne API path is invalid")
    if any(any(ord(ch) < 33 or ord(ch) == 127 for ch in part) for part in parts):
        raise HackerOneClientError("HackerOne API path contains unsafe characters")
    return value


def _read_bounded(response, limit: int) -> bytes:
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise HackerOneClientError("HackerOne response exceeds configured size limit")
    return payload


class HackerOneClient:
    def __init__(self, credentials: HackerOneCredentials | None = None):
        self.credentials = credentials or load_hackerone_credentials()

    def get_json(
        self,
        path: str,
        query: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_path = _validate_path(path)
        url = urllib.parse.urljoin(_API_ROOT, safe_path)
        if not url.startswith(_API_ROOT):
            raise HackerOneClientError("HackerOne API path escaped fixed origin")
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        request = urllib.request.Request(
            url,
            method="GET",
            headers=self.credentials.headers(),
        )
        opener = urllib.request.build_opener(
            _NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )
        timeout = _timeout_seconds()
        try:
            response = opener.open(request, timeout=timeout)
            status = int(getattr(response, "status", response.getcode()))
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "application/json" not in content_type:
                raise HackerOneClientError("HackerOne response is not JSON")
            raw = _read_bounded(response, _max_response_bytes())
        except HackerOneClientError:
            raise
        except urllib.error.HTTPError as exc:
            raise HackerOneClientError(
                f"HackerOne returned HTTP {exc.code}",
                status_code=int(exc.code),
            ) from exc
        except urllib.error.URLError as exc:
            raise HackerOneClientError("HackerOne transport connection failed") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise HackerOneClientError("HackerOne transport timed out") from exc
        except OSError as exc:
            raise HackerOneClientError("HackerOne transport I/O failed") from exc

        if status < 200 or status >= 300:
            raise HackerOneClientError(f"HackerOne returned HTTP {status}", status_code=status)
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HackerOneClientError("HackerOne response contains invalid JSON") from exc
        if not isinstance(document, dict):
            raise HackerOneClientError("HackerOne response must be a JSON object")
        return document

    def get_all_pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page_number in range(1, _MAX_PAGES + 1):
            document = self.get_json(
                path,
                {"page[number]": page_number, "page[size]": _PAGE_SIZE},
            )
            data = document.get("data")
            if not isinstance(data, list):
                raise HackerOneClientError("HackerOne paginated response has no data list")
            if any(not isinstance(item, dict) for item in data):
                raise HackerOneClientError("HackerOne paginated response contains invalid items")
            items.extend(data)
            if len(data) < _PAGE_SIZE:
                return items
        raise HackerOneClientError("HackerOne pagination exceeded safety limit")


_HANDLE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")
_PROGRAM_FIELDS = (
    "handle",
    "name",
    "policy",
    "submission_state",
    "state",
    "offers_bounties",
    "open_scope",
    "fast_payments",
    "gold_standard_safe_harbor",
)


@dataclass(frozen=True)
class HackerOneProgramSnapshot:
    handle: str
    program: dict[str, Any]
    document: dict[str, Any]
    scope_exclusions: tuple[dict[str, Any], ...]
    preview: dict[str, Any]
    snapshot_sha256: str


def _validate_handle(handle: str) -> str:
    if not isinstance(handle, str) or not 1 <= len(handle) <= 128:
        raise HackerOneClientError("HackerOne program handle is invalid")
    if handle != handle.strip() or handle != handle.lower():
        raise HackerOneClientError("HackerOne program handle is invalid")
    if handle[0] == "-" or any(ch not in _HANDLE_CHARS for ch in handle):
        raise HackerOneClientError("HackerOne program handle is invalid")
    return handle


def _canonical_resource(resource: dict[str, Any]) -> str:
    return json.dumps(resource, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sorted_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(resources, key=_canonical_resource)


def _program_projection(document: dict[str, Any], expected_handle: str) -> dict[str, Any]:
    data = document.get("data")
    if not isinstance(data, dict):
        raise HackerOneClientError("HackerOne program response has no resource object")
    attributes = data.get("attributes")
    if not isinstance(attributes, dict):
        raise HackerOneClientError("HackerOne program response has no attributes object")
    remote_handle = attributes.get("handle")
    if remote_handle != expected_handle:
        raise HackerOneClientError("HackerOne program handle mismatch")
    projected = {field: attributes.get(field) for field in _PROGRAM_FIELDS}
    if not isinstance(projected["name"], str) or not projected["name"].strip():
        raise HackerOneClientError("HackerOne program name is invalid")
    if not isinstance(projected["policy"], str):
        raise HackerOneClientError("HackerOne program policy is invalid")
    return projected


def _preview_dict(document: dict[str, Any]) -> dict[str, Any]:
    try:
        preview = import_hackerone_structured_scope(document)
    except HackerOneScopeImportError as exc:
        raise HackerOneClientError("HackerOne structured scope is invalid") from exc
    return {
        "complete": preview.complete,
        "allowed_targets": list(preview.allowed_targets),
        "denied_targets": list(preview.denied_targets),
        "conflicts": list(preview.conflicts),
        "unsupported": list(preview.unsupported),
        "assets": [asdict(asset) for asset in preview.assets],
    }


def fetch_hackerone_program_snapshot(
    handle: str,
    *,
    client: HackerOneClient | None = None,
) -> HackerOneProgramSnapshot:
    safe_handle = _validate_handle(handle)
    api = client or HackerOneClient()
    base = f"hackers/programs/{safe_handle}"

    program_document = api.get_json(base)
    program = _program_projection(program_document, safe_handle)
    scopes = _sorted_resources(api.get_all_pages(f"{base}/structured_scopes"))
    exclusions = _sorted_resources(api.get_all_pages(f"{base}/scope_exclusions"))
    document = {"data": scopes, "links": {}}
    preview = _preview_dict(document)

    canonical = {
        "handle": safe_handle,
        "program": program,
        "structured_scopes": scopes,
        "scope_exclusions": exclusions,
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    return HackerOneProgramSnapshot(
        handle=safe_handle,
        program=program,
        document=document,
        scope_exclusions=tuple(exclusions),
        preview=preview,
        snapshot_sha256=digest,
    )
