from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


STRIX_MANIFEST_ADMISSION_SCHEMA = "strix-manifest-admission-v1"

_MAX_ENTRIES = 128
_MAX_ENTRY_PATH_BYTES = 512
_MAX_INLINE_FILE_BYTES = 1024 * 1024
_MAX_TOTAL_INLINE_FILE_BYTES = 4 * 1024 * 1024
_MAX_ENV_VARS = 64
_MAX_ENV_KEY_BYTES = 128
_MAX_ENV_VALUE_BYTES = 4096
_MAX_TOTAL_ENV_VALUE_BYTES = 16 * 1024
_MAX_LOCAL_SOURCE_PATH_BYTES = 4096

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class StrixManifestAdmissionError(RuntimeError):
    pass


@dataclass(frozen=True)
class StrixManifestEntryPlan:
    path: str
    kind: str
    content_bytes: int | None
    content_sha256: str | None
    local_source_present: bool
    local_source_path_redacted: bool
    local_source_path_sha256: str | None
    local_source_content_sha256: str | None
    local_source_content_inspected: bool
    content_uploaded: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrixManifestEnvironmentPlan:
    key: str
    value_bytes: int
    value_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrixManifestAdmissionPlan:
    schema: str
    manifest_version: int
    root: str
    entries: tuple[StrixManifestEntryPlan, ...]
    environment: tuple[StrixManifestEnvironmentPlan, ...]
    entry_count: int
    inline_file_count: int
    local_dir_count: int
    inline_file_bytes: int
    environment_value_bytes: int
    host_paths_included: bool
    raw_file_content_included: bool
    filesystem_io_performed: bool
    manifest_materialized: bool
    upload_enabled: bool
    manifest_digest: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entries"] = [item.to_dict() for item in self.entries]
        payload["environment"] = [
            item.to_dict() for item in self.environment
        ]
        return payload


def _safe_text(value: object, *, name: str, max_bytes: int) -> str:
    if not isinstance(value, str):
        raise StrixManifestAdmissionError(f"{name} must be text")
    encoded = value.encode("utf-8")
    if (
        not encoded
        or len(encoded) > max_bytes
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise StrixManifestAdmissionError(f"{name} is invalid")
    return value


def _normalize_entry_path(value: object) -> str:
    if isinstance(value, Path):
        raw_value = value.as_posix()
    elif isinstance(value, str):
        raw_value = value
    else:
        raise StrixManifestAdmissionError(
            "manifest entry path must be text or Path"
        )
    raw = _safe_text(
        raw_value,
        name="manifest entry path",
        max_bytes=_MAX_ENTRY_PATH_BYTES,
    )
    if "\\" in raw:
        raise StrixManifestAdmissionError(
            "manifest entry path must use POSIX separators"
        )
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise StrixManifestAdmissionError(
            "manifest entry path must be workspace-relative"
        )
    parts = path.parts
    if (
        not parts
        or any(part in {"", ".", ".."} for part in parts)
        or str(path) != raw.strip("/")
    ):
        raise StrixManifestAdmissionError("manifest entry path is invalid")
    return path.as_posix()


def _entry_kind(entry: object) -> str:
    kind = getattr(entry, "type", None)
    if kind not in {"file", "local_dir"}:
        raise StrixManifestAdmissionError(
            "manifest entry type is unsupported"
        )
    return str(kind)


def _plan_file(path: str, entry: object) -> StrixManifestEntryPlan:
    content = getattr(entry, "content", None)
    if not isinstance(content, (bytes, bytearray)):
        raise StrixManifestAdmissionError(
            "manifest file content must be bytes"
        )
    payload = bytes(content)
    if len(payload) > _MAX_INLINE_FILE_BYTES:
        raise StrixManifestAdmissionError(
            "manifest inline file exceeds byte limit"
        )
    return StrixManifestEntryPlan(
        path=path,
        kind="file",
        content_bytes=len(payload),
        content_sha256=hashlib.sha256(payload).hexdigest(),
        local_source_present=False,
        local_source_path_redacted=False,
        local_source_path_sha256=None,
        local_source_content_sha256=None,
        local_source_content_inspected=False,
        content_uploaded=False,
    )


def _plan_local_dir(path: str, entry: object) -> StrixManifestEntryPlan:
    source = getattr(entry, "src", None)
    if source is None:
        raise StrixManifestAdmissionError(
            "manifest local directory source is unavailable"
        )
    source_text = str(source)
    _safe_text(
        source_text,
        name="manifest local directory source",
        max_bytes=_MAX_LOCAL_SOURCE_PATH_BYTES,
    )
    return StrixManifestEntryPlan(
        path=path,
        kind="local_dir",
        content_bytes=None,
        content_sha256=None,
        local_source_present=True,
        local_source_path_redacted=True,
        local_source_path_sha256=hashlib.sha256(
            source_text.encode("utf-8")
        ).hexdigest(),
        local_source_content_sha256=None,
        local_source_content_inspected=False,
        content_uploaded=False,
    )


def _plan_entries(entries: object) -> tuple[StrixManifestEntryPlan, ...]:
    if not isinstance(entries, Mapping):
        raise StrixManifestAdmissionError(
            "manifest entries must be a mapping"
        )
    if len(entries) > _MAX_ENTRIES:
        raise StrixManifestAdmissionError(
            "manifest entry count exceeds limit"
        )

    planned: list[StrixManifestEntryPlan] = []
    seen: set[str] = set()
    total_inline_bytes = 0
    for raw_path, entry in entries.items():
        path = _normalize_entry_path(raw_path)
        if path in seen:
            raise StrixManifestAdmissionError(
                "manifest contains duplicate normalized entry paths"
            )
        seen.add(path)

        kind = _entry_kind(entry)
        if kind == "file":
            item = _plan_file(path, entry)
            total_inline_bytes += int(item.content_bytes or 0)
            if total_inline_bytes > _MAX_TOTAL_INLINE_FILE_BYTES:
                raise StrixManifestAdmissionError(
                    "manifest inline content exceeds total byte limit"
                )
        else:
            item = _plan_local_dir(path, entry)
        planned.append(item)

    return tuple(sorted(planned, key=lambda item: item.path))


def _plan_environment(
    environment: object,
) -> tuple[StrixManifestEnvironmentPlan, ...]:
    values = getattr(environment, "value", None)
    if not isinstance(values, Mapping):
        raise StrixManifestAdmissionError(
            "manifest environment must expose a value mapping"
        )
    if len(values) > _MAX_ENV_VARS:
        raise StrixManifestAdmissionError(
            "manifest environment variable count exceeds limit"
        )

    planned: list[StrixManifestEnvironmentPlan] = []
    total_bytes = 0
    for raw_key, raw_value in values.items():
        key = _safe_text(
            raw_key,
            name="manifest environment key",
            max_bytes=_MAX_ENV_KEY_BYTES,
        )
        if not _ENV_KEY_RE.fullmatch(key):
            raise StrixManifestAdmissionError(
                "manifest environment key is invalid"
            )
        if not isinstance(raw_value, str):
            raise StrixManifestAdmissionError(
                "manifest environment supports literal string values only"
            )
        value_bytes = raw_value.encode("utf-8")
        if len(value_bytes) > _MAX_ENV_VALUE_BYTES:
            raise StrixManifestAdmissionError(
                "manifest environment value exceeds byte limit"
            )
        total_bytes += len(value_bytes)
        if total_bytes > _MAX_TOTAL_ENV_VALUE_BYTES:
            raise StrixManifestAdmissionError(
                "manifest environment exceeds total byte limit"
            )
        planned.append(
            StrixManifestEnvironmentPlan(
                key=key,
                value_bytes=len(value_bytes),
                value_sha256=hashlib.sha256(value_bytes).hexdigest(),
            )
        )
    return tuple(sorted(planned, key=lambda item: item.key))


def _assert_empty_collection(manifest: object, name: str) -> None:
    value = getattr(manifest, name, ())
    if value:
        raise StrixManifestAdmissionError(
            f"manifest {name} are unsupported by the prepared remote backend"
        )


def _canonical_payload(
    *,
    version: int,
    root: str,
    entries: tuple[StrixManifestEntryPlan, ...],
    environment: tuple[StrixManifestEnvironmentPlan, ...],
) -> bytes:
    payload = {
        "schema": STRIX_MANIFEST_ADMISSION_SCHEMA,
        "manifest_version": version,
        "root": root,
        "entries": [item.to_dict() for item in entries],
        "environment": [item.to_dict() for item in environment],
        "host_paths_included": False,
        "raw_file_content_included": False,
        "filesystem_io_performed": False,
        "manifest_materialized": False,
        "upload_enabled": False,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def build_strix_manifest_admission_plan(
    manifest: object,
) -> StrixManifestAdmissionPlan:
    if manifest is None:
        raise StrixManifestAdmissionError("manifest is required")

    version = getattr(manifest, "version", None)
    root = getattr(manifest, "root", None)
    if version != 1:
        raise StrixManifestAdmissionError(
            "manifest version is unsupported"
        )
    if root != "/workspace":
        raise StrixManifestAdmissionError(
            "manifest root must be /workspace"
        )

    _assert_empty_collection(manifest, "users")
    _assert_empty_collection(manifest, "groups")
    _assert_empty_collection(manifest, "extra_path_grants")

    entries = _plan_entries(getattr(manifest, "entries", None))
    environment = _plan_environment(
        getattr(manifest, "environment", None)
    )
    inline_file_bytes = sum(
        int(item.content_bytes or 0)
        for item in entries
        if item.kind == "file"
    )
    environment_value_bytes = sum(
        item.value_bytes for item in environment
    )
    canonical = _canonical_payload(
        version=version,
        root=root,
        entries=entries,
        environment=environment,
    )
    return StrixManifestAdmissionPlan(
        schema=STRIX_MANIFEST_ADMISSION_SCHEMA,
        manifest_version=version,
        root=root,
        entries=entries,
        environment=environment,
        entry_count=len(entries),
        inline_file_count=sum(item.kind == "file" for item in entries),
        local_dir_count=sum(item.kind == "local_dir" for item in entries),
        inline_file_bytes=inline_file_bytes,
        environment_value_bytes=environment_value_bytes,
        host_paths_included=False,
        raw_file_content_included=False,
        filesystem_io_performed=False,
        manifest_materialized=False,
        upload_enabled=False,
        manifest_digest=hashlib.sha256(canonical).hexdigest(),
    )
