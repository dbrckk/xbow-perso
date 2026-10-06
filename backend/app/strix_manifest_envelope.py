from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


STRIX_MANIFEST_ENVELOPE_SCHEMA = "strix-manifest-envelope-v1"
STRIX_MANIFEST_MAX_FILES = 256
STRIX_MANIFEST_MAX_FILE_BYTES = 1024 * 1024
STRIX_MANIFEST_MAX_TOTAL_BYTES = 8 * 1024 * 1024
STRIX_MANIFEST_MAX_PATH_BYTES = 512

_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._+@=-]{1,128}$")


class StrixManifestEnvelopeError(ValueError):
    pass


@dataclass(frozen=True)
class StrixManifestFile:
    path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrixManifestEnvelope:
    schema: str
    files: tuple[StrixManifestFile, ...]
    file_count: int
    total_bytes: int
    content_digest: str
    host_paths_included: bool
    file_contents_included: bool
    executable_materialization_allowed: bool
    materialization_enabled: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["files"] = [item.to_dict() for item in self.files]
        return payload


def _normalize_path(value: object) -> str:
    if not isinstance(value, str):
        raise StrixManifestEnvelopeError("manifest path must be text")
    if "\\" in value or value.startswith("/") or value.endswith("/"):
        raise StrixManifestEnvelopeError("manifest path must be workspace-relative")
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > STRIX_MANIFEST_MAX_PATH_BYTES:
        raise StrixManifestEnvelopeError("manifest path exceeds bounds")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise StrixManifestEnvelopeError("manifest path contains control characters")
    parts = value.split("/")
    if any(
        part in {"", ".", ".."} or not _PATH_SEGMENT_RE.fullmatch(part)
        for part in parts
    ):
        raise StrixManifestEnvelopeError("manifest path contains unsafe segments")
    return "/".join(parts)


def _content_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        content = value
    elif isinstance(value, bytearray):
        content = bytes(value)
    elif isinstance(value, str):
        content = value.encode("utf-8")
    else:
        raise StrixManifestEnvelopeError("manifest file content must be bytes or text")
    if len(content) > STRIX_MANIFEST_MAX_FILE_BYTES:
        raise StrixManifestEnvelopeError("manifest file exceeds byte limit")
    return content


def build_strix_manifest_envelope(
    files: Mapping[str, object] | Iterable[tuple[str, object]],
) -> StrixManifestEnvelope:
    if isinstance(files, Mapping):
        items = list(files.items())
    else:
        items = list(files)
    if len(items) > STRIX_MANIFEST_MAX_FILES:
        raise StrixManifestEnvelopeError("manifest exceeds file-count limit")

    normalized: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    total_bytes = 0
    for raw_path, raw_content in items:
        path = _normalize_path(raw_path)
        if path in seen:
            raise StrixManifestEnvelopeError("manifest contains duplicate path")
        seen.add(path)
        content = _content_bytes(raw_content)
        total_bytes += len(content)
        if total_bytes > STRIX_MANIFEST_MAX_TOTAL_BYTES:
            raise StrixManifestEnvelopeError("manifest exceeds total byte limit")
        normalized.append((path, content))

    normalized.sort(key=lambda item: item[0])
    descriptors = tuple(
        StrixManifestFile(
            path=path,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        for path, content in normalized
    )
    canonical = json.dumps(
        {
            "schema": STRIX_MANIFEST_ENVELOPE_SCHEMA,
            "files": [item.to_dict() for item in descriptors],
            "file_count": len(descriptors),
            "total_bytes": total_bytes,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return StrixManifestEnvelope(
        schema=STRIX_MANIFEST_ENVELOPE_SCHEMA,
        files=descriptors,
        file_count=len(descriptors),
        total_bytes=total_bytes,
        content_digest=hashlib.sha256(canonical).hexdigest(),
        host_paths_included=False,
        file_contents_included=False,
        executable_materialization_allowed=False,
        materialization_enabled=False,
    )


def verify_strix_manifest_envelope(
    envelope: StrixManifestEnvelope,
    files: Mapping[str, object] | Iterable[tuple[str, object]],
) -> None:
    rebuilt = build_strix_manifest_envelope(files)
    if rebuilt != envelope:
        raise StrixManifestEnvelopeError("manifest envelope does not match supplied files")
