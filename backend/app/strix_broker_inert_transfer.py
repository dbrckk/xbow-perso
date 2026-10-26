"""Broker-only verification of inert Strix manifest bytes over isolated RPC.

This is not a scanner dispatcher. No public route exposes this orchestration.
No materialization, host file access or target networking is performed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from .strix_execution_contract import (
    StrixExecutionContract,
    StrixExecutionContractError,
    authorize_strix_contract_request,
)
from .strix_manifest_admission import (
    StrixManifestAdmissionError,
    build_strix_manifest_admission_plan,
)
from .strix_runner_manifest_ticket import (
    StrixRunnerManifestTicketError,
    build_strix_runner_manifest_ticket,
    validate_strix_runner_manifest_ticket_secret,
)
from .strix_runner_rpc import (
    RUNNER_RPC_MAX_FILE_CHUNK_BYTES,
    RUNNER_RPC_PROTOCOL,
    sign_runner_rpc_request,
)


_RUNNER_BASE = "http://strix-runner:8092"
_MAX_REPLY_BYTES = 8192
_MAX_INLINE_FILE_BYTES = 1024 * 1024
_MAX_TOTAL_BYTES = 4 * 1024 * 1024
_SESSION_ID_RE = re.compile(r"^prepared-[0-9a-f]{32}$")
_PLAN_KEYS = (
    "schema", "manifest_version", "root", "entries", "environment",
    "host_paths_included", "raw_file_content_included",
    "filesystem_io_performed", "manifest_materialized", "upload_enabled",
)
_ALLOWED_PATHS = frozenset({
    "/v1/session/prepare", "/v1/session/plan-receipt",
    "/v1/session/file-chunk", "/v1/session/release",
    "/v1/session/preparation-status",
})


class StrixInertTransferError(RuntimeError):
    """A fail-closed, deliberately non-executing broker transfer error."""


class StrixInertTransportUncertain(StrixInertTransferError):
    """The runner may have processed an RPC before the reply was lost."""


@dataclass(frozen=True)
class InertManifestVerificationReceipt:
    contract_hash: str
    manifest_digest: str
    verified_inline_files: int
    verified_inline_bytes: int
    session_released: bool = True
    manifest_materialized: bool = False
    active_execution_enabled: bool = False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _keys() -> tuple[str, str, str]:
    verification = os.environ.get("XBOW_STRIX_BROKER_HMAC_KEY", "")
    admission = os.environ.get("XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY", "")
    transport = os.environ.get("XBOW_STRIX_RUNNER_RPC_HMAC_KEY", "")
    if not verification or len(verification.encode("utf-8")) > 4096:
        raise StrixInertTransferError("broker contract key unavailable")
    try:
        validate_strix_runner_manifest_ticket_secret(admission)
    except (StrixRunnerManifestTicketError, UnicodeError) as exc:
        raise StrixInertTransferError("runner admission key unavailable") from exc
    try:
        length = len(transport.encode("utf-8"))
    except UnicodeError as exc:
        raise StrixInertTransferError("runner transport key unavailable") from exc
    if not 32 <= length <= 4096:
        raise StrixInertTransferError("runner transport key unavailable")
    return verification, admission, transport


def _post_runner(
    path: str, payload: dict[str, Any], *, key: str, status: int,
) -> dict[str, Any]:
    if path not in _ALLOWED_PATHS:
        raise StrixInertTransferError("unsupported runner operation")
    body = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    if len(body) > 1024 * 1024:
        raise StrixInertTransferError("runner payload exceeds limit")
    timestamp = int(time.time())
    nonce = secrets.token_hex(16)
    signature = sign_runner_rpc_request(
        method="POST", path=path, body=body, secret=key,
        timestamp=timestamp, nonce=nonce,
    )
    request = urllib.request.Request(
        _RUNNER_BASE + path,
        data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Xbow-Runner-Timestamp": str(timestamp),
            "X-Xbow-Runner-Nonce": nonce,
            "X-Xbow-Runner-Signature": signature,
        },
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect(),
    )
    try:
        with opener.open(request, timeout=5) as response:
            data = response.read(_MAX_REPLY_BYTES + 1)
            code = response.status
    except urllib.error.HTTPError as exc:
        raise StrixInertTransferError(
            f"runner rejected {path} (HTTP {exc.code})"
        ) from exc
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise StrixInertTransportUncertain(
            f"runner outcome unknown at {path}"
        ) from exc
    if code != status or len(data) > _MAX_REPLY_BYTES:
        raise StrixInertTransferError("runner reply status or size invalid")
    try:
        result = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise StrixInertTransferError("runner reply is not JSON") from exc
    if (
        not isinstance(result, dict)
        or result.get("protocol") != RUNNER_RPC_PROTOCOL
        or result.get("manifest_materialized") is not False
        or result.get("active_execution_enabled") is not False
    ):
        raise StrixInertTransferError("runner violated inert reply contract")
    return result


def _canonical_plan(files: Mapping[str, bytes]) -> tuple[str, Any]:
    if not isinstance(files, Mapping) or len(files) > 128:
        raise StrixInertTransferError("invalid file collection")
    total = 0
    entries: dict[str, Any] = {}
    for path, data in files.items():
        if not isinstance(path, str) or not isinstance(data, bytes):
            raise StrixInertTransferError("only inline bytes and paths are accepted")
        if len(data) > _MAX_INLINE_FILE_BYTES:
            raise StrixInertTransferError("inline file exceeds byte limit")
        total += len(data)
        if total > _MAX_TOTAL_BYTES:
            raise StrixInertTransferError("inline files exceed aggregate limit")
        entries[path] = SimpleNamespace(type="file", content=data)
    manifest = SimpleNamespace(
        version=1, root="/workspace", entries=entries,
        environment=SimpleNamespace(value={}),
        users=[], groups=[], extra_path_grants=[],
    )
    try:
        plan = build_strix_manifest_admission_plan(manifest)
    except StrixManifestAdmissionError as exc:
        raise StrixInertTransferError("invalid inline-file manifest") from exc
    metadata = plan.to_dict()
    canonical = json.dumps(
        {key: metadata[key] for key in _PLAN_KEYS},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != plan.manifest_digest:
        raise StrixInertTransferError("canonical manifest digest mismatch")
    if len(canonical.encode("utf-8")) > 256 * 1024:
        raise StrixInertTransferError("canonical manifest plan too large")
    return canonical, plan


def verify_inert_manifest_files(
    *,
    contract: StrixExecutionContract,
    image: str,
    exposed_ports: Sequence[int],
    files: Mapping[str, bytes],
) -> InertManifestVerificationReceipt:
    """Verify all inline file bytes against a broker-signed plan and release.

    No automatic retries: a lost response can mean the runner consumed a
    one-shot ticket or chunk. Any ambiguity fails closed; a prepared session
    is released best-effort or naturally expires after 900 seconds.
    """
    verification_key, admission_key, rpc_key = _keys()
    try:
        authorize_strix_contract_request(
            contract, target=contract.primary_target,
            requested_rps=contract.max_requests_per_second,
            verification_secret=verification_key,
        )
    except (StrixExecutionContractError, AttributeError, TypeError) as exc:
        raise StrixInertTransferError("execution contract rejected") from exc

    plan_json, plan = _canonical_plan(files)
    request_id = "inert-" + secrets.token_hex(16)
    descriptor = {
        "schema": plan.schema,
        "contract_hash": contract.contract_hash,
        "request_id": request_id,
        "image": image,
        "exposed_ports": list(exposed_ports),
        "manifest_digest": plan.manifest_digest,
        "entry_count": plan.entry_count,
        "inline_file_count": plan.inline_file_count,
        "local_dir_count": plan.local_dir_count,
        "inline_file_bytes": plan.inline_file_bytes,
        "environment_value_bytes": plan.environment_value_bytes,
        "host_paths_included": False,
        "raw_file_content_included": False,
        "filesystem_io_performed": False,
        "manifest_materialized": False,
        "upload_enabled": False,
        "active_execution_enabled": False,
    }
    try:
        ticket = build_strix_runner_manifest_ticket(
            descriptor, signing_secret=admission_key,
        ).to_dict()
    except (StrixRunnerManifestTicketError, TypeError, ValueError) as exc:
        raise StrixInertTransferError("manifest admission rejected") from exc

    # Never re-send an ambiguous preparation ticket. A transport error may
    # have occurred after the runner atomically consumed it. The read-only
    # lookup uses the same request identity and cannot extend the session.
    try:
        prepared = _post_runner(
            "/v1/session/prepare",
            {
                "schema": RUNNER_RPC_PROTOCOL,
                "request_id": request_id,
                "image": image,
                "exposed_ports": list(exposed_ports),
                "manifest_digest": plan.manifest_digest,
                "admission": ticket,
            },
            key=rpc_key, status=201,
        )
    except StrixInertTransportUncertain:
        prepared = _post_runner(
            "/v1/session/preparation-status",
            {
                "schema": RUNNER_RPC_PROTOCOL,
                "request_id": "lookup-" + secrets.token_hex(16),
                "preparation_request_id": request_id,
                "contract_hash": contract.contract_hash,
                "manifest_digest": plan.manifest_digest,
            },
            key=rpc_key, status=200,
        )
    session_id = prepared.get("session_id")
    if (
        not isinstance(session_id, str)
        or not _SESSION_ID_RE.fullmatch(session_id)
        or prepared.get("status") != "prepared"
        or prepared.get("contract_hash") != contract.contract_hash
        or prepared.get("manifest_digest") != plan.manifest_digest
        or type(prepared.get("expires_in_seconds")) is not int
        or not 1 <= prepared["expires_in_seconds"] <= 900
    ):
        raise StrixInertTransferError("runner preparation receipt invalid")

    base = {
        "schema": RUNNER_RPC_PROTOCOL,
        "session_id": session_id,
        "contract_hash": contract.contract_hash,
        "manifest_digest": plan.manifest_digest,
    }
    try:
        receipt = _post_runner(
            "/v1/session/plan-receipt",
            {
                **base,
                "request_id": "plan-" + secrets.token_hex(16),
                "plan_json": plan_json,
            },
            key=rpc_key, status=200,
        )
        if (
            receipt.get("status") != "plan_verified"
            or receipt.get("session_id") != session_id
            or receipt.get("manifest_digest") != plan.manifest_digest
            or receipt.get("plan_bytes_verified") != len(plan_json.encode("utf-8"))
            or receipt.get("file_contents_received") is not False
        ):
            raise StrixInertTransferError("runner plan receipt invalid")

        ordered_entries = [entry for entry in plan.entries if entry.kind == "file"]
        for number, entry in enumerate(ordered_entries, start=1):
            data = files[entry.path]
            offsets = range(0, len(data), RUNNER_RPC_MAX_FILE_CHUNK_BYTES)
            for offset in offsets if data else (0,):
                chunk = data[offset:offset + RUNNER_RPC_MAX_FILE_CHUNK_BYTES]
                final = offset + len(chunk) == len(data)
                response = _post_runner(
                    "/v1/session/file-chunk",
                    {
                        **base,
                        "request_id": "chunk-" + secrets.token_hex(16),
                        "file_path": entry.path,
                        "content_sha256": entry.content_sha256,
                        "offset": offset,
                        "chunk_base64": base64.b64encode(chunk).decode("ascii"),
                        "final": final,
                    },
                    key=rpc_key, status=200,
                )
                if (
                    response.get("session_id") != session_id
                    or response.get("file_path") != entry.path
                    or response.get("file_bytes_received") != offset + len(chunk)
                    or response.get("file_sha256_verified") is not final
                    or response.get("verified_inline_files") != (number if final else number - 1)
                    or response.get("all_inline_files_verified") is not (
                        final and number == plan.inline_file_count
                    )
                    or response.get("status") != (
                        "file_verified" if final else "chunk_received"
                    )
                ):
                    raise StrixInertTransferError("runner file receipt invalid")
    finally:
        released = _post_runner(
            "/v1/session/release",
            {
                "schema": RUNNER_RPC_PROTOCOL,
                "request_id": "release-" + secrets.token_hex(16),
                "session_id": session_id,
                "contract_hash": contract.contract_hash,
            },
            key=rpc_key, status=200,
        )
        if released.get("status") != "released" or released.get("session_id") != session_id:
            raise StrixInertTransferError("runner release receipt invalid")
    return InertManifestVerificationReceipt(
        contract_hash=contract.contract_hash,
        manifest_digest=plan.manifest_digest,
        verified_inline_files=plan.inline_file_count,
        verified_inline_bytes=plan.inline_file_bytes,
    )
