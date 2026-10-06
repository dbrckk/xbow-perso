from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

STRIX_MANIFEST_ADMISSION_SCHEMA = "strix-manifest-admission-v1"


STRIX_RUNNER_MANIFEST_TICKET_SCHEMA = "strix-runner-manifest-ticket-v1"
STRIX_RUNNER_MANIFEST_TICKET_MIN_SECRET_BYTES = 32
STRIX_RUNNER_MANIFEST_TICKET_MAX_SECRET_BYTES = 4096

_SIGNATURE_DOMAIN = b"xbow:strix-runner-manifest-ticket:v1\x00"
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_MAX_ENTRIES = 128
_MAX_INLINE_FILE_BYTES = 4 * 1024 * 1024
_MAX_ENVIRONMENT_VALUE_BYTES = 16 * 1024


class StrixRunnerManifestTicketError(RuntimeError):
    pass


@dataclass(frozen=True)
class StrixRunnerManifestTicket:
    schema: str
    manifest_schema: str
    contract_hash: str
    request_id: str
    image: str
    exposed_ports: tuple[int, ...]
    manifest_digest: str
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
    active_execution_enabled: bool
    signature_alg: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["exposed_ports"] = list(self.exposed_ports)
        return payload


def _secret_bytes(secret: str) -> bytes:
    if not isinstance(secret, str):
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket secret must be text"
        )
    encoded = secret.encode("utf-8")
    if len(encoded) < STRIX_RUNNER_MANIFEST_TICKET_MIN_SECRET_BYTES:
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket secret must be at least 32 bytes"
        )
    if len(encoded) > STRIX_RUNNER_MANIFEST_TICKET_MAX_SECRET_BYTES:
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket secret exceeds maximum size"
        )
    return encoded


def validate_strix_runner_manifest_ticket_secret(secret: str) -> None:
    _secret_bytes(secret)


def _valid_image(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 512
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise StrixRunnerManifestTicketError(
            "runner manifest image is invalid"
        )
    return value


def _valid_ports(value: Sequence[int]) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or len(value) > 16:
        raise StrixRunnerManifestTicketError(
            "runner manifest exposed ports are invalid"
        )
    ports: list[int] = []
    for port in value:
        if (
            not isinstance(port, int)
            or isinstance(port, bool)
            or not 1 <= port <= 65535
        ):
            raise StrixRunnerManifestTicketError(
                "runner manifest exposed port is invalid"
            )
        ports.append(port)
    if len(set(ports)) != len(ports):
        raise StrixRunnerManifestTicketError(
            "runner manifest exposed ports contain duplicates"
        )
    return tuple(ports)


def _validate_descriptor(values: Mapping[str, Any]) -> dict[str, Any]:
    if values.get("schema") != STRIX_MANIFEST_ADMISSION_SCHEMA:
        raise StrixRunnerManifestTicketError(
            "runner manifest admission schema is unsupported"
        )

    contract_hash = values.get("contract_hash")
    if not isinstance(contract_hash, str) or not _SHA256_RE.fullmatch(contract_hash):
        raise StrixRunnerManifestTicketError(
            "runner manifest contract hash is invalid"
        )
    request_id = values.get("request_id")
    if not isinstance(request_id, str) or not _ID_RE.fullmatch(request_id):
        raise StrixRunnerManifestTicketError(
            "runner manifest request id is invalid"
        )

    image = _valid_image(values.get("image"))
    ports = _valid_ports(values.get("exposed_ports", ()))
    digest = values.get("manifest_digest")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise StrixRunnerManifestTicketError(
            "runner manifest digest is invalid"
        )

    entry_count = values.get("entry_count")
    inline_file_count = values.get("inline_file_count")
    local_dir_count = values.get("local_dir_count")
    inline_file_bytes = values.get("inline_file_bytes")
    environment_value_bytes = values.get("environment_value_bytes")
    for name, value, maximum in (
        ("entry_count", entry_count, _MAX_ENTRIES),
        ("inline_file_count", inline_file_count, _MAX_ENTRIES),
        ("local_dir_count", local_dir_count, _MAX_ENTRIES),
        ("inline_file_bytes", inline_file_bytes, _MAX_INLINE_FILE_BYTES),
        (
            "environment_value_bytes",
            environment_value_bytes,
            _MAX_ENVIRONMENT_VALUE_BYTES,
        ),
    ):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= maximum
        ):
            raise StrixRunnerManifestTicketError(
                f"runner manifest {name} is invalid"
            )
    if inline_file_count + local_dir_count != entry_count:
        raise StrixRunnerManifestTicketError(
            "runner manifest entry counts are inconsistent"
        )

    if (
        values.get("host_paths_included") is not False
        or values.get("raw_file_content_included") is not False
        or values.get("filesystem_io_performed") is not False
        or values.get("manifest_materialized") is not False
        or values.get("upload_enabled") is not False
        or values.get("active_execution_enabled") is not False
    ):
        raise StrixRunnerManifestTicketError(
            "runner manifest safety invariants changed"
        )

    return {
        "schema": STRIX_RUNNER_MANIFEST_TICKET_SCHEMA,
        "manifest_schema": STRIX_MANIFEST_ADMISSION_SCHEMA,
        "contract_hash": contract_hash,
        "request_id": request_id,
        "image": image,
        "exposed_ports": ports,
        "manifest_digest": digest,
        "entry_count": entry_count,
        "inline_file_count": inline_file_count,
        "local_dir_count": local_dir_count,
        "inline_file_bytes": inline_file_bytes,
        "environment_value_bytes": environment_value_bytes,
        "host_paths_included": False,
        "raw_file_content_included": False,
        "filesystem_io_performed": False,
        "manifest_materialized": False,
        "upload_enabled": False,
        "active_execution_enabled": False,
    }


def _canonical_bytes(values: Mapping[str, Any]) -> bytes:
    payload = {
        "schema": values["schema"],
        "manifest_schema": values["manifest_schema"],
        "contract_hash": values["contract_hash"],
        "request_id": values["request_id"],
        "image": values["image"],
        "exposed_ports": list(values["exposed_ports"]),
        "manifest_digest": values["manifest_digest"],
        "entry_count": values["entry_count"],
        "inline_file_count": values["inline_file_count"],
        "local_dir_count": values["local_dir_count"],
        "inline_file_bytes": values["inline_file_bytes"],
        "environment_value_bytes": values["environment_value_bytes"],
        "host_paths_included": values["host_paths_included"],
        "raw_file_content_included": values["raw_file_content_included"],
        "filesystem_io_performed": values["filesystem_io_performed"],
        "manifest_materialized": values["manifest_materialized"],
        "upload_enabled": values["upload_enabled"],
        "active_execution_enabled": values["active_execution_enabled"],
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def build_strix_runner_manifest_ticket(
    manifest_descriptor: Mapping[str, Any],
    *,
    signing_secret: str,
) -> StrixRunnerManifestTicket:
    unsigned = _validate_descriptor(manifest_descriptor)
    secret = _secret_bytes(signing_secret)
    signature = hmac.new(
        secret,
        _SIGNATURE_DOMAIN + _canonical_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    return StrixRunnerManifestTicket(
        **unsigned,
        signature_alg="hmac-sha256",
        signature=signature,
    )


def verify_strix_runner_manifest_ticket(
    ticket_payload: Mapping[str, Any],
    *,
    request_id: str,
    image: str,
    exposed_ports: Sequence[int],
    manifest_digest: str,
    verification_secret: str,
) -> StrixRunnerManifestTicket:
    expected_keys = {
        "schema",
        "manifest_schema",
        "contract_hash",
        "request_id",
        "image",
        "exposed_ports",
        "manifest_digest",
        "entry_count",
        "inline_file_count",
        "local_dir_count",
        "inline_file_bytes",
        "environment_value_bytes",
        "host_paths_included",
        "raw_file_content_included",
        "filesystem_io_performed",
        "manifest_materialized",
        "upload_enabled",
        "active_execution_enabled",
        "signature_alg",
        "signature",
    }
    if set(ticket_payload) != expected_keys:
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket shape is invalid"
        )
    if ticket_payload.get("schema") != STRIX_RUNNER_MANIFEST_TICKET_SCHEMA:
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket schema is unsupported"
        )
    if ticket_payload.get("manifest_schema") != STRIX_MANIFEST_ADMISSION_SCHEMA:
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket admission schema is unsupported"
        )
    if ticket_payload.get("signature_alg") != "hmac-sha256":
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket signature algorithm is unsupported"
        )
    signature = ticket_payload.get("signature")
    if not isinstance(signature, str) or not _SHA256_RE.fullmatch(signature):
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket signature is invalid"
        )

    descriptor = {
        "schema": ticket_payload["manifest_schema"],
        "contract_hash": ticket_payload["contract_hash"],
        "request_id": ticket_payload["request_id"],
        "image": ticket_payload["image"],
        "exposed_ports": ticket_payload["exposed_ports"],
        "manifest_digest": ticket_payload["manifest_digest"],
        "entry_count": ticket_payload["entry_count"],
        "inline_file_count": ticket_payload["inline_file_count"],
        "local_dir_count": ticket_payload["local_dir_count"],
        "inline_file_bytes": ticket_payload["inline_file_bytes"],
        "environment_value_bytes": ticket_payload["environment_value_bytes"],
        "host_paths_included": ticket_payload["host_paths_included"],
        "raw_file_content_included": ticket_payload["raw_file_content_included"],
        "filesystem_io_performed": ticket_payload["filesystem_io_performed"],
        "manifest_materialized": ticket_payload["manifest_materialized"],
        "upload_enabled": ticket_payload["upload_enabled"],
        "active_execution_enabled": ticket_payload["active_execution_enabled"],
    }
    unsigned = _validate_descriptor(descriptor)

    secret = _secret_bytes(verification_secret)
    expected_signature = hmac.new(
        secret,
        _SIGNATURE_DOMAIN + _canonical_bytes(unsigned),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket signature mismatch"
        )

    expected_ports = _valid_ports(exposed_ports)
    if (
        ticket_payload["request_id"] != request_id
        or ticket_payload["image"] != _valid_image(image)
        or tuple(ticket_payload["exposed_ports"]) != expected_ports
        or ticket_payload["manifest_digest"] != manifest_digest
    ):
        raise StrixRunnerManifestTicketError(
            "runner manifest ticket does not match create request"
        )

    return StrixRunnerManifestTicket(
        **{
            key: (
                tuple(ticket_payload[key])
                if key == "exposed_ports"
                else ticket_payload[key]
            )
            for key in expected_keys
        }
    )
