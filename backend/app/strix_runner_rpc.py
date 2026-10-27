from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import socket
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .strix_runner_attestation import attest_strix_runner
from .strix_runner_exec_ticket import (
    StrixRunnerExecTicketError,
    validate_strix_runner_exec_ticket_secret,
    verify_strix_runner_exec_ticket,
)
from .strix_runner_manifest_ticket import (
    StrixRunnerManifestTicketError,
    validate_strix_runner_manifest_ticket_secret,
    verify_strix_runner_manifest_ticket,
)


RUNNER_RPC_PROTOCOL = "strix-runner-rpc-v1"
RUNNER_RPC_PORT = 8092
RUNNER_RPC_MAX_BODY_BYTES = 1024 * 1024
RUNNER_RPC_AUTH_WINDOW_SECONDS = 30
RUNNER_RPC_MAX_NONCES = 4096
RUNNER_RPC_SOCKET_TIMEOUT_SECONDS = 5.0
RUNNER_RPC_READ_DEADLINE_SECONDS = 10.0
RUNNER_RPC_MAX_CONCURRENT_CONNECTIONS = 16
RUNNER_RPC_MIN_SECRET_BYTES = 32
RUNNER_RPC_MAX_SECRET_BYTES = 4096
RUNNER_RPC_PREPARED_SESSION_TTL_SECONDS = 900
RUNNER_RPC_MAX_PREPARED_SESSIONS = 128
RUNNER_RPC_MAX_PREPARATION_TICKETS = 1024
RUNNER_RPC_MAX_RELEASE_RECEIPTS = 1024
RUNNER_RPC_REPLAY_DB_PATH = "/var/lib/strix-runner/preparation-replay.sqlite3"
RUNNER_RPC_MAX_FILE_CHUNK_BYTES = 64 * 1024

_MUTATION_PATHS = {
    "/v1/session/create",
    "/v1/session/exec",
    "/v1/session/resolve-port",
    "/v1/session/delete",
    "/v1/session/prepare",
    "/v1/session/release",
    "/v1/session/plan-receipt",
    "/v1/session/file-chunk",
    "/v1/session/preparation-status",
    "/v1/session/verification-status",
    "/v1/session/release-status",
}
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RunnerRpcResponse:
    status: int
    json_body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class _InertFileProof:
    expected_digest: str
    expected_bytes: int
    received_bytes: int = 0
    hash_state: Any = field(default_factory=hashlib.sha256)
    verified: bool = False
    failed: bool = False


@dataclass(frozen=True)
class _PreparedSession:
    session_id: str
    preparation_request_id: str
    contract_hash: str
    manifest_digest: str
    expires_at: float
    entry_count: int
    inline_file_count: int
    local_dir_count: int
    inline_file_bytes: int
    environment_value_bytes: int
    plan_verified: bool = False
    file_proofs: dict[str, _InertFileProof] = field(default_factory=dict)


@dataclass(frozen=True)
class _ReleasedSession:
    session_id: str
    release_request_id: str
    contract_hash: str
    manifest_digest: str
    expires_at: float


class _DurablePreparationReplay:
    """Durable, bounded, transactional replay journal containing no manifest data."""

    def __init__(self, path: str) -> None:
        if path != ":memory:" and (not os.path.isabs(path) or os.path.islink(path)):
            raise ValueError("unsafe runner replay database path")
        self._conn = sqlite3.connect(
            path, timeout=2.0, isolation_level=None, check_same_thread=False
        )
        try:
            self._conn.execute("PRAGMA busy_timeout=2000")
            self._conn.execute("PRAGMA journal_mode=DELETE")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA max_page_count=1024")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS consumed_tickets ("
                "contract_hash TEXT NOT NULL, request_id TEXT NOT NULL, "
                "expires_at INTEGER NOT NULL, "
                "PRIMARY KEY (contract_hash, request_id)) WITHOUT ROWID"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS consumed_tickets_expiry "
                "ON consumed_tickets (expires_at)"
            )
            if not self.ready():
                raise sqlite3.DatabaseError("runner replay database integrity invalid")
            if path != ":memory:":
                os.chmod(path, 0o600)
        except BaseException:
            self._conn.close()
            raise

    def ready(self) -> bool:
        try:
            return self._conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
        except sqlite3.Error:
            return False

    def consume(
        self, *, contract_hash: str, request_id: str,
        expires_at: int, now: int,
    ) -> str:
        # Called under _prepared_lock; BEGIN IMMEDIATE serializes DB writers.
        cursor = self._conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "DELETE FROM consumed_tickets WHERE expires_at <= ?", (now,)
            )
            prior = cursor.execute(
                "SELECT 1 FROM consumed_tickets "
                "WHERE contract_hash = ? AND request_id = ?",
                (contract_hash, request_id),
            ).fetchone()
            if prior is not None:
                outcome = "replayed"
            elif cursor.execute("SELECT COUNT(*) FROM consumed_tickets").fetchone()[0] >= (
                RUNNER_RPC_MAX_PREPARATION_TICKETS
            ):
                outcome = "capacity"
            else:
                cursor.execute(
                    "INSERT INTO consumed_tickets "
                    "(contract_hash, request_id, expires_at) VALUES (?, ?, ?)",
                    (contract_hash, request_id, expires_at),
                )
                outcome = "consumed"
            cursor.execute("COMMIT")
            return outcome
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                cursor.execute("ROLLBACK")
            raise
        finally:
            cursor.close()


class RunnerRpcService:
    def __init__(
        self,
        *,
        secret: str | None,
        admission_secret: str | None,
        active_execution: bool,
        now: Callable[[], float] = time.time,
        replay_db_path: str | None = None,
    ) -> None:
        if secret:
            _runner_rpc_secret_bytes(secret)
        if admission_secret:
            validate_strix_runner_exec_ticket_secret(admission_secret)
            validate_strix_runner_manifest_ticket_secret(admission_secret)
        self._secret = secret if secret else None
        self._admission_secret = admission_secret if admission_secret else None
        self._active_execution = bool(active_execution)
        self._now = now
        self._nonces: OrderedDict[str, float] = OrderedDict()
        self._nonce_lock = threading.Lock()
        # Inert metadata only: no files, subprocesses, ports or target network.
        # State is process-local and expires even if the broker never releases it.
        self._prepared_sessions: dict[str, _PreparedSession] = {}
        # Bounded, ephemeral receipts for lost release responses. Never
        # persist session identities, upload data, or extend session TTLs.
        self._released_sessions: OrderedDict[str, _ReleasedSession] = OrderedDict()
        self._preparation_tickets: OrderedDict[tuple[str, str], float] = (
            OrderedDict()
        )
        self._prepared_lock = threading.Lock()
        self._replay_store = (
            _DurablePreparationReplay(replay_db_path)
            if replay_db_path is not None else None
        )

    def handle(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> RunnerRpcResponse:
        normalized_method = str(method).upper()
        normalized_headers = {
            str(key).lower(): str(value)
            for key, value in headers.items()
        }

        if normalized_method == "GET" and path == "/healthz":
            return RunnerRpcResponse(
                status=200,
                json_body={
                    "status": "ok",
                    "protocol": RUNNER_RPC_PROTOCOL,
                    "active_execution_enabled": self._active_execution,
                    "exec_admission_required": True,
                    "manifest_admission_required": True,
                    "implemented_operations": [],
                },
            )

        if normalized_method == "GET" and path == "/readyz":
            if not self._secret:
                return _error(503, "rpc_key_unavailable")
            if not self._admission_secret:
                return _error(503, "exec_admission_key_unavailable")
            if self._replay_store is None or not self._replay_store.ready():
                return _error(503, "preparation_replay_store_unavailable")
            return RunnerRpcResponse(
                status=200,
                json_body={
                    "status": "ready",
                    "protocol": RUNNER_RPC_PROTOCOL,
                    "active_execution_enabled": self._active_execution,
                    "exec_admission_required": True,
                    "exec_admission_configured": True,
                    "manifest_admission_required": True,
                    "manifest_admission_configured": True,
                    "implemented_operations": [],
                    "inert_preparation_operations": [
                        "prepare", "release", "plan-receipt", "file-chunk",
                        "preparation-status", "verification-status",
                        "release-status",
                    ],
                    "durable_preparation_replay": True,
                },
            )

        if path not in _MUTATION_PATHS:
            return _error(404, "not_found")
        if normalized_method != "POST":
            return _error(405, "method_not_allowed")

        auth_error = self._authenticate(
            method=normalized_method,
            path=path,
            headers=normalized_headers,
            body=body,
        )
        if auth_error is not None:
            return auth_error

        if len(body) > RUNNER_RPC_MAX_BODY_BYTES:
            return _error(413, "request_too_large")
        content_type = normalized_headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            return _error(415, "unsupported_media_type")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return _error(400, "invalid_request")
        if not isinstance(payload, dict):
            return _error(400, "invalid_request")
        if not _validate_operation_payload(path, payload):
            return _error(400, "invalid_request")

        if path == "/v1/session/prepare":
            return self._prepare_session(payload)
        if path == "/v1/session/preparation-status":
            return self._preparation_status(payload)
        if path == "/v1/session/verification-status":
            return self._verification_status(payload)
        if path == "/v1/session/release-status":
            return self._release_status(payload)
        if path == "/v1/session/release":
            return self._release_session(payload)
        if path == "/v1/session/plan-receipt":
            return self._receive_plan(payload)
        if path == "/v1/session/file-chunk":
            return self._receive_file_chunk(payload)

        if path == "/v1/session/create":
            if not self._admission_secret:
                return _error(503, "manifest_admission_key_unavailable")
            try:
                verify_strix_runner_manifest_ticket(
                    payload["admission"],
                    request_id=payload["request_id"],
                    image=payload["image"],
                    exposed_ports=payload["exposed_ports"],
                    manifest_digest=payload["manifest_digest"],
                    verification_secret=self._admission_secret,
                    now=self._now(),
                )
            except StrixRunnerManifestTicketError:
                return _error(403, "manifest_admission_rejected")

        if path == "/v1/session/exec":
            if not self._admission_secret:
                return _error(503, "exec_admission_key_unavailable")
            try:
                verify_strix_runner_exec_ticket(
                    payload["admission"],
                    session_id=payload["session_id"],
                    request_id=payload["request_id"],
                    argv=payload["argv"],
                    timeout_seconds=payload["timeout_seconds"],
                    verification_secret=self._admission_secret,
                )
            except StrixRunnerExecTicketError:
                return _error(403, "exec_admission_rejected")

        if not self._active_execution:
            return _error(503, "active_execution_disabled")
        return _error(501, "rpc_operation_not_implemented")

    def _prune_prepared_sessions(self, now: float) -> None:
        # Called only under _prepared_lock. Monotonic time avoids an NTP clock
        # adjustment extending the lifetime of a preparation record.
        expired = [
            key for key, record in self._prepared_sessions.items()
            if now >= record.expires_at
        ]
        for key in expired:
            del self._prepared_sessions[key]
        for key, receipt in list(self._released_sessions.items()):
            if now >= receipt.expires_at:
                del self._released_sessions[key]
        while self._preparation_tickets:
            key, expiry = next(iter(self._preparation_tickets.items()))
            if now < expiry:
                break
            del self._preparation_tickets[key]

    def _prepare_session(self, payload: dict[str, Any]) -> RunnerRpcResponse:
        if self._active_execution:
            return _error(409, "inert_session_required")
        if not self._admission_secret:
            return _error(503, "manifest_admission_key_unavailable")
        if self._replay_store is None:
            return _error(503, "preparation_replay_store_unavailable")
        try:
            ticket = verify_strix_runner_manifest_ticket(
                payload["admission"],
                request_id=payload["request_id"],
                image=payload["image"],
                exposed_ports=payload["exposed_ports"],
                manifest_digest=payload["manifest_digest"],
                verification_secret=self._admission_secret,
                now=self._now(),
            )
        except StrixRunnerManifestTicketError:
            return _error(403, "manifest_admission_rejected")

        now = time.monotonic()
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        ticket_id = (ticket.contract_hash, ticket.request_id)
        with self._prepared_lock:
            self._prune_prepared_sessions(now)
            if ticket_id in self._preparation_tickets:
                return _error(409, "preparation_ticket_replayed")
            if len(self._prepared_sessions) >= RUNNER_RPC_MAX_PREPARED_SESSIONS:
                return _error(503, "prepared_session_capacity_reached")
            if len(self._preparation_tickets) >= RUNNER_RPC_MAX_PREPARATION_TICKETS:
                return _error(503, "preparation_ticket_capacity_reached")
            try:
                outcome = self._replay_store.consume(
                    contract_hash=ticket.contract_hash,
                    request_id=ticket.request_id,
                    expires_at=ticket.expires_at,
                    now=int(self._now()),
                )
            except (sqlite3.Error, OSError):
                return _error(503, "preparation_replay_store_unavailable")
            if outcome == "replayed":
                return _error(409, "preparation_ticket_replayed")
            if outcome == "capacity":
                return _error(503, "preparation_ticket_capacity_reached")
            session_id = f"prepared-{secrets.token_hex(16)}"
            while session_id in self._prepared_sessions or session_id in self._released_sessions:
                session_id = f"prepared-{secrets.token_hex(16)}"
            expires_at = now + RUNNER_RPC_PREPARED_SESSION_TTL_SECONDS
            self._prepared_sessions[session_id] = _PreparedSession(
                session_id=session_id,
                preparation_request_id=ticket.request_id,
                contract_hash=ticket.contract_hash,
                manifest_digest=ticket.manifest_digest,
                expires_at=expires_at,
                entry_count=ticket.entry_count,
                inline_file_count=ticket.inline_file_count,
                local_dir_count=ticket.local_dir_count,
                inline_file_bytes=ticket.inline_file_bytes,
                environment_value_bytes=ticket.environment_value_bytes,
            )
            # Ticket replay stays rejected even if the session is released.
            self._preparation_tickets[ticket_id] = expires_at

        return RunnerRpcResponse(
            status=201,
            json_body={
                "status": "prepared",
                "protocol": RUNNER_RPC_PROTOCOL,
                "session_id": session_id,
                "contract_hash": ticket.contract_hash,
                "manifest_digest": ticket.manifest_digest,
                "expires_in_seconds": RUNNER_RPC_PREPARED_SESSION_TTL_SECONDS,
                "manifest_materialized": False,
                "active_execution_enabled": False,
            },
        )

    def _preparation_status(self, payload: dict[str, Any]) -> RunnerRpcResponse:
        """Recover a live inert session after a lost prepare response.

        Does not consume a ticket, issue a new ticket, or refresh the TTL.
        The caller must know the fresh preparation request id as well as the
        exact signed contract and manifest digests.
        """
        if self._active_execution:
            return _error(409, "inert_session_required")
        now = time.monotonic()
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        with self._prepared_lock:
            self._prune_prepared_sessions(now)
            for item in self._prepared_sessions.values():
                if not hmac.compare_digest(
                    item.preparation_request_id, payload["preparation_request_id"]
                ):
                    continue
                if not hmac.compare_digest(
                    item.contract_hash, payload["contract_hash"]
                ):
                    return _error(403, "prepared_session_contract_mismatch")
                if not hmac.compare_digest(
                    item.manifest_digest, payload["manifest_digest"]
                ):
                    return _error(403, "manifest_digest_mismatch")
                return RunnerRpcResponse(
                    status=200,
                    json_body={
                        "status": "prepared",
                        "protocol": RUNNER_RPC_PROTOCOL,
                        "session_id": item.session_id,
                        "contract_hash": item.contract_hash,
                        "manifest_digest": item.manifest_digest,
                        "expires_in_seconds": math.ceil(item.expires_at - now),
                        "manifest_materialized": False,
                        "active_execution_enabled": False,
                    },
                )
        return _error(404, "prepared_session_not_found")

    def _receive_plan(self, payload: dict[str, Any]) -> RunnerRpcResponse:
        if self._active_execution:
            return _error(409, "inert_session_required")
        now = time.monotonic()
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        with self._prepared_lock:
            self._prune_prepared_sessions(now)
            item = self._prepared_sessions.get(payload["session_id"])
            if item is None:
                return _error(404, "prepared_session_not_found")
            if not hmac.compare_digest(item.contract_hash, payload["contract_hash"]):
                return _error(403, "prepared_session_contract_mismatch")
            if not hmac.compare_digest(item.manifest_digest, payload["manifest_digest"]):
                return _error(403, "manifest_digest_mismatch")
            if item.plan_verified:
                return _error(409, "manifest_plan_already_verified")
            try:
                verified_bytes = verify_canonical_manifest_plan(
                    payload["plan_json"],
                    manifest_digest=item.manifest_digest,
                    entry_count=item.entry_count,
                    inline_file_count=item.inline_file_count,
                    local_dir_count=item.local_dir_count,
                    inline_file_bytes=item.inline_file_bytes,
                    environment_value_bytes=item.environment_value_bytes,
                )
            except ValueError:
                return _error(400, "manifest_plan_rejected")
            # Only signed metadata is retained. Actual file bytes never survive
            # beyond the current authenticated request.
            plan = json.loads(payload["plan_json"])
            file_proofs = {
                entry["path"]: _InertFileProof(
                    expected_digest=entry["content_sha256"],
                    expected_bytes=entry["content_bytes"],
                )
                for entry in plan["entries"] if entry["kind"] == "file"
            }
            self._prepared_sessions[item.session_id] = replace(
                item, plan_verified=True, file_proofs=file_proofs,
            )
        return RunnerRpcResponse(
            status=200,
            json_body={
                "status": "plan_verified",
                "protocol": RUNNER_RPC_PROTOCOL,
                "session_id": item.session_id,
                "manifest_digest": item.manifest_digest,
                "plan_bytes_verified": verified_bytes,
                "file_contents_received": False,
                "manifest_materialized": False,
                "active_execution_enabled": False,
            },
        )

    def _verification_status(self, payload: dict[str, Any]) -> RunnerRpcResponse:
        """Attest only the accepted byte prefix; no raw content leaves memory."""
        if self._active_execution:
            return _error(409, "inert_session_required")
        now = time.monotonic()
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        with self._prepared_lock:
            self._prune_prepared_sessions(now)
            item = self._prepared_sessions.get(payload["session_id"])
            if item is None:
                return _error(404, "prepared_session_not_found")
            if not hmac.compare_digest(item.contract_hash, payload["contract_hash"]):
                return _error(403, "prepared_session_contract_mismatch")
            if not hmac.compare_digest(item.manifest_digest, payload["manifest_digest"]):
                return _error(403, "manifest_digest_mismatch")
            path = payload["file_path"]
            proof = None
            if path is not None:
                if not item.plan_verified:
                    return _error(409, "manifest_plan_not_verified")
                proof = item.file_proofs.get(path)
                if proof is None:
                    return _error(404, "manifest_file_not_found")
            verified_files = sum(p.verified for p in item.file_proofs.values())
            return RunnerRpcResponse(
                status=200,
                json_body={
                    "status": "verification_status",
                    "protocol": RUNNER_RPC_PROTOCOL,
                    "session_id": item.session_id,
                    "contract_hash": item.contract_hash,
                    "manifest_digest": item.manifest_digest,
                    "plan_verified": item.plan_verified,
                    "inline_file_count": item.inline_file_count,
                    "verified_inline_files": verified_files,
                    "all_inline_files_verified": (
                        item.plan_verified and verified_files == item.inline_file_count
                    ),
                    "file_path": path,
                    "file_bytes_received": proof.received_bytes if proof else None,
                    "file_prefix_sha256": (
                        proof.hash_state.hexdigest() if proof else None
                    ),
                    "file_sha256_verified": proof.verified if proof else None,
                    "file_failed": proof.failed if proof else None,
                    "manifest_materialized": False,
                    "active_execution_enabled": False,
                },
            )

    def _receive_file_chunk(self, payload: dict[str, Any]) -> RunnerRpcResponse:
        """Inert, ordered, digest-verified byte transfer; never materialize."""
        if self._active_execution:
            return _error(409, "inert_session_required")
        now = time.monotonic()
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        with self._prepared_lock:
            self._prune_prepared_sessions(now)
            item = self._prepared_sessions.get(payload["session_id"])
            if item is None:
                return _error(404, "prepared_session_not_found")
            if not hmac.compare_digest(item.contract_hash, payload["contract_hash"]):
                return _error(403, "prepared_session_contract_mismatch")
            if not hmac.compare_digest(item.manifest_digest, payload["manifest_digest"]):
                return _error(403, "manifest_digest_mismatch")
            if not item.plan_verified:
                return _error(409, "manifest_plan_not_verified")
            proof = item.file_proofs.get(payload["file_path"])
            if proof is None:
                return _error(404, "manifest_file_not_found")
            if not hmac.compare_digest(proof.expected_digest, payload["content_sha256"]):
                return _error(403, "manifest_file_digest_mismatch")
            if proof.verified or proof.failed:
                return _error(409, "manifest_file_already_finalized")
            if payload["offset"] != proof.received_bytes:
                return _error(409, "manifest_file_offset_mismatch")
            try:
                content = _decode_inert_chunk(payload["chunk_base64"])
            except ValueError:
                return _error(400, "manifest_file_chunk_invalid")
            next_bytes = proof.received_bytes + len(content)
            if next_bytes > proof.expected_bytes:
                return _error(413, "manifest_file_size_exceeded")
            is_last = payload["final"]
            if (not content and not is_last) or (
                is_last != (next_bytes == proof.expected_bytes)
            ):
                return _error(400, "manifest_file_finalization_invalid")
            proof.hash_state.update(content)
            proof.received_bytes = next_bytes
            if is_last:
                if not hmac.compare_digest(
                    proof.hash_state.hexdigest(), proof.expected_digest
                ):
                    proof.failed = True
                    return _error(422, "manifest_file_content_mismatch")
                proof.verified = True
            verified_files = sum(record.verified for record in item.file_proofs.values())
            return RunnerRpcResponse(
                status=200,
                json_body={
                    "status": "file_verified" if is_last else "chunk_received",
                    "protocol": RUNNER_RPC_PROTOCOL,
                    "session_id": item.session_id,
                    "file_path": payload["file_path"],
                    "file_bytes_received": proof.received_bytes,
                    "file_prefix_sha256": proof.hash_state.hexdigest(),
                    "file_sha256_verified": proof.verified,
                    "verified_inline_files": verified_files,
                    "all_inline_files_verified": (
                        verified_files == item.inline_file_count
                    ),
                    "manifest_materialized": False,
                    "active_execution_enabled": False,
                },
            )

    def _release_session(self, payload: dict[str, Any]) -> RunnerRpcResponse:
        if self._active_execution:
            return _error(409, "inert_session_required")
        now = time.monotonic()
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        with self._prepared_lock:
            self._prune_prepared_sessions(now)
            item = self._prepared_sessions.get(payload["session_id"])
            if item is None:
                return _error(404, "prepared_session_not_found")
            if not hmac.compare_digest(item.contract_hash, payload["contract_hash"]):
                return _error(403, "prepared_session_contract_mismatch")
            del self._prepared_sessions[item.session_id]
            if len(self._released_sessions) >= RUNNER_RPC_MAX_RELEASE_RECEIPTS:
                # A lost receipt can then fail closed; resource release itself
                # must never be blocked by a saturated evidence cache.
                self._released_sessions.popitem(last=False)
            self._released_sessions[item.session_id] = _ReleasedSession(
                session_id=item.session_id,
                release_request_id=payload["request_id"],
                contract_hash=item.contract_hash,
                manifest_digest=item.manifest_digest,
                expires_at=item.expires_at,
            )
        return RunnerRpcResponse(
            status=200,
            json_body={
                "status": "released",
                "protocol": RUNNER_RPC_PROTOCOL,
                "session_id": item.session_id,
                "manifest_materialized": False,
                "active_execution_enabled": False,
            },
        )

    def _release_status(self, payload: dict[str, Any]) -> RunnerRpcResponse:
        """Prove an exact release, not mere absence or natural expiry."""
        if self._active_execution:
            return _error(409, "inert_session_required")
        now = time.monotonic()
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        with self._prepared_lock:
            self._prune_prepared_sessions(now)
            item = self._released_sessions.get(payload["session_id"])
            if item is None:
                return _error(404, "release_receipt_not_found")
            if not hmac.compare_digest(item.contract_hash, payload["contract_hash"]):
                return _error(403, "prepared_session_contract_mismatch")
            if not hmac.compare_digest(item.manifest_digest, payload["manifest_digest"]):
                return _error(403, "manifest_digest_mismatch")
            if not hmac.compare_digest(
                item.release_request_id, payload["release_request_id"]
            ):
                return _error(404, "release_receipt_not_found")
            return RunnerRpcResponse(
                status=200,
                json_body={
                    "status": "released",
                    "protocol": RUNNER_RPC_PROTOCOL,
                    "session_id": item.session_id,
                    "release_request_id": item.release_request_id,
                    "contract_hash": item.contract_hash,
                    "manifest_digest": item.manifest_digest,
                    "manifest_materialized": False,
                    "active_execution_enabled": False,
                },
            )

    def _authenticate(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> RunnerRpcResponse | None:
        if not self._secret:
            return _error(503, "rpc_key_unavailable")

        timestamp_raw = headers.get("x-xbow-runner-timestamp")
        nonce = headers.get("x-xbow-runner-nonce")
        signature = headers.get("x-xbow-runner-signature")
        if not timestamp_raw or not nonce or not signature:
            return _error(401, "authentication_required")

        try:
            timestamp = int(timestamp_raw)
        except ValueError:
            return _error(401, "authentication_required")
        if not _NONCE_RE.fullmatch(nonce):
            return _error(401, "authentication_required")
        if not _SIGNATURE_RE.fullmatch(signature):
            return _error(401, "authentication_required")

        now = float(self._now())
        if not math.isfinite(now):
            return _error(503, "clock_unavailable")
        if abs(now - timestamp) > RUNNER_RPC_AUTH_WINDOW_SECONDS:
            return _error(401, "timestamp_out_of_window")

        expected = sign_runner_rpc_request(
            method=method,
            path=path,
            body=body,
            secret=self._secret,
            timestamp=timestamp,
            nonce=nonce,
        )
        if not hmac.compare_digest(signature, expected):
            return _error(401, "signature_mismatch")

        with self._nonce_lock:
            self._prune_nonces(now)
            if nonce in self._nonces:
                return _error(409, "replay_detected")
            if len(self._nonces) >= RUNNER_RPC_MAX_NONCES:
                return _error(503, "replay_cache_saturated")
            self._nonces[nonce] = now
            self._nonces.move_to_end(nonce)
        return None

    def _prune_nonces(self, now: float) -> None:
        cutoff = now - RUNNER_RPC_AUTH_WINDOW_SECONDS
        while self._nonces:
            _nonce, seen_at = next(iter(self._nonces.items()))
            if seen_at >= cutoff:
                break
            self._nonces.popitem(last=False)


def _runner_rpc_secret_bytes(secret: str) -> bytes:
    if not isinstance(secret, str):
        raise ValueError("runner RPC secret must be text")
    encoded = secret.encode("utf-8")
    if len(encoded) < RUNNER_RPC_MIN_SECRET_BYTES:
        raise ValueError("runner RPC secret must be at least 32 bytes")
    if len(encoded) > RUNNER_RPC_MAX_SECRET_BYTES:
        raise ValueError("runner RPC secret exceeds maximum size")
    return encoded


def sign_runner_rpc_request(
    *,
    method: str,
    path: str,
    body: bytes,
    secret: str,
    timestamp: int,
    nonce: str,
) -> str:
    secret_bytes = _runner_rpc_secret_bytes(secret)
    body_digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        (
            RUNNER_RPC_PROTOCOL,
            str(method).upper(),
            str(path),
            str(int(timestamp)),
            str(nonce),
            body_digest,
        )
    ).encode("utf-8")
    return hmac.new(
        secret_bytes,
        canonical,
        hashlib.sha256,
    ).hexdigest()


def sign_runner_rpc_response(
    *,
    method: str,
    path: str,
    request_body: bytes,
    response_body: bytes,
    status: int,
    secret: str,
    timestamp: int,
    nonce: str,
) -> str:
    """Authenticate exact response bytes and status for a single signed RPC."""
    fields = (
        "strix-runner-rpc-response-v1",
        str(method).upper(),
        str(path),
        str(int(timestamp)),
        str(nonce),
        hashlib.sha256(request_body).hexdigest(),
        str(int(status)),
        hashlib.sha256(response_body).hexdigest(),
    )
    return hmac.new(
        _runner_rpc_secret_bytes(secret),
        "\n".join(fields).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def configure_runner_rpc_socket(connection: Any) -> None:
    connection.settimeout(RUNNER_RPC_SOCKET_TIMEOUT_SECONDS)


def _error(status: int, code: str) -> RunnerRpcResponse:
    return RunnerRpcResponse(
        status=status,
        json_body={
            "status": "error",
            "error": code,
            "protocol": RUNNER_RPC_PROTOCOL,
        },
    )


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _valid_port(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 1 <= value <= 65535
    )


def _exact_keys(payload: dict[str, Any], expected: set[str]) -> bool:
    return set(payload) == expected


def _valid_common(payload: dict[str, Any]) -> bool:
    return (
        payload.get("schema") == RUNNER_RPC_PROTOCOL
        and _valid_id(payload.get("request_id"))
    )


_PLAN_SCHEMA = "strix-manifest-admission-v1"
_PLAN_MAX_BYTES = 256 * 1024
_PLAN_KEYS = {
    "schema", "manifest_version", "root", "entries", "environment",
    "host_paths_included", "raw_file_content_included",
    "filesystem_io_performed", "manifest_materialized", "upload_enabled",
}
_PLAN_ENTRY_KEYS = {
    "path", "kind", "content_bytes", "content_sha256",
    "local_source_present", "local_source_path_redacted",
    "local_source_path_sha256", "local_source_content_sha256",
    "local_source_content_inspected", "content_uploaded",
}
_PLAN_ENV_KEYS = {"key", "value_bytes", "value_sha256"}
_PLAN_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _plan_count(value: object, upper: int) -> bool:
    return type(value) is int and 0 <= value <= upper


def _plan_path(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 512:
        return False
    if (
        value.startswith("/") or value.endswith("/") or "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        return False
    try:
        return len(value.encode("utf-8")) <= 512
    except UnicodeEncodeError:
        return False


def verify_canonical_manifest_plan(
    plan_json: str,
    *,
    manifest_digest: str,
    entry_count: int,
    inline_file_count: int,
    local_dir_count: int,
    inline_file_bytes: int,
    environment_value_bytes: int,
) -> int:
    """Check exact received canonical metadata bytes; never load file contents."""
    if not isinstance(plan_json, str) or len(plan_json) > _PLAN_MAX_BYTES:
        raise ValueError("manifest plan length exceeds limit")
    try:
        raw = plan_json.encode("utf-8")
        if len(raw) > _PLAN_MAX_BYTES:
            raise ValueError("manifest plan length exceeds limit")
        plan = json.loads(raw)
        canonical = json.dumps(
            plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise ValueError("manifest plan must be canonical UTF-8 JSON") from exc
    if not isinstance(plan, dict) or set(plan) != _PLAN_KEYS or canonical != raw:
        raise ValueError("manifest plan shape or encoding invalid")
    if (
        not _valid_digest(manifest_digest)
        or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), manifest_digest)
    ):
        raise ValueError("manifest plan does not match signed digest")
    if (
        plan["schema"] != _PLAN_SCHEMA
        or type(plan["manifest_version"]) is not int
        or plan["manifest_version"] != 1
        or plan["root"] != "/workspace"
        or any(plan[key] is not False for key in (
            "host_paths_included", "raw_file_content_included",
            "filesystem_io_performed", "manifest_materialized", "upload_enabled",
        ))
    ):
        raise ValueError("unsafe manifest plan invariants")

    entries = plan["entries"]
    env = plan["environment"]
    if not isinstance(entries, list) or len(entries) > 128:
        raise ValueError("invalid manifest plan entries")
    if not isinstance(env, list) or len(env) > 64:
        raise ValueError("invalid manifest plan environment")

    paths: set[str] = set()
    files, local_dirs, file_bytes = 0, 0, 0
    for item in entries:
        if not isinstance(item, dict) or set(item) != _PLAN_ENTRY_KEYS:
            raise ValueError("invalid plan entry metadata")
        path = item["path"]
        if not _plan_path(path) or path in paths:
            raise ValueError("invalid plan entry path")
        parts = path.split("/")
        if any("/".join(parts[:i]) in paths for i in range(1, len(parts))):
            raise ValueError("plan entry paths overlap")
        paths.add(path)
        if (
            item["local_source_content_inspected"] is not False
            or item["content_uploaded"] is not False
            or item["local_source_content_sha256"] is not None
        ):
            raise ValueError("unsafe plan entry metadata")
        if item["kind"] == "file":
            if (
                not _plan_count(item["content_bytes"], 1024 * 1024)
                or not _valid_digest(item["content_sha256"])
                or item["local_source_present"] is not False
                or item["local_source_path_redacted"] is not False
                or item["local_source_path_sha256"] is not None
            ):
                raise ValueError("invalid inline file metadata")
            files += 1
            file_bytes += item["content_bytes"]
        elif item["kind"] == "local_dir":
            if (
                item["content_bytes"] is not None
                or item["content_sha256"] is not None
                or item["local_source_present"] is not True
                or item["local_source_path_redacted"] is not True
                or not _valid_digest(item["local_source_path_sha256"])
            ):
                raise ValueError("invalid local directory metadata")
            local_dirs += 1
        else:
            raise ValueError("unsupported manifest entry type")
    if (
        [item["path"] for item in entries] != sorted(paths)
        or file_bytes > 4 * 1024 * 1024
    ):
        raise ValueError("manifest entry order or byte limit invalid")

    env_keys: set[str] = set()
    env_bytes = 0
    for item in env:
        if not isinstance(item, dict) or set(item) != _PLAN_ENV_KEYS:
            raise ValueError("invalid environment metadata")
        key = item["key"]
        if (
            not isinstance(key, str) or not _PLAN_ENV_KEY_RE.fullmatch(key)
            or key in env_keys
            or not _plan_count(item["value_bytes"], 4096)
            or not _valid_digest(item["value_sha256"])
        ):
            raise ValueError("invalid environment metadata")
        env_keys.add(key)
        env_bytes += item["value_bytes"]
    if (
        [item["key"] for item in env] != sorted(env_keys)
        or env_bytes > 16 * 1024
    ):
        raise ValueError("environment order or byte limit invalid")
    if (
        len(entries) != entry_count or files != inline_file_count
        or local_dirs != local_dir_count or file_bytes != inline_file_bytes
        or env_bytes != environment_value_bytes
    ):
        raise ValueError("manifest plan differs from signed ticket counts")
    return len(raw)


def _decode_inert_chunk(encoded: str) -> bytes:
    """Decode canonical Base64 with a strict pre-allocation size bound."""
    if not isinstance(encoded, str):
        raise ValueError("file chunk must be base64")
    if len(encoded) > ((RUNNER_RPC_MAX_FILE_CHUNK_BYTES + 2) // 3) * 4:
        raise ValueError("file chunk exceeds limit")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("file chunk is not valid base64") from exc
    if (
        len(content) > RUNNER_RPC_MAX_FILE_CHUNK_BYTES
        or base64.b64encode(content).decode("ascii") != encoded
    ):
        raise ValueError("file chunk is not canonical base64")
    return content


def _validate_operation_payload(path: str, payload: dict[str, Any]) -> bool:
    if not _valid_common(payload):
        return False

    if path in {"/v1/session/create", "/v1/session/prepare"}:
        if not _exact_keys(
            payload,
            {
                "schema",
                "request_id",
                "image",
                "exposed_ports",
                "manifest_digest",
                "admission",
            },
        ):
            return False
        image = payload.get("image")
        ports = payload.get("exposed_ports")
        admission = payload.get("admission")
        if (
            not isinstance(image, str)
            or not 1 <= len(image) <= 512
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in image)
            or not isinstance(ports, list)
            or not 0 <= len(ports) <= 16
            or any(not _valid_port(port) for port in ports)
            or len(set(ports)) != len(ports)
            or not _valid_digest(payload.get("manifest_digest"))
            or not isinstance(admission, dict)
        ):
            return False
        return True

    if path == "/v1/session/exec":
        if not _exact_keys(
            payload,
            {
                "schema",
                "request_id",
                "session_id",
                "argv",
                "timeout_seconds",
                "admission",
            },
        ):
            return False
        argv = payload.get("argv")
        timeout = payload.get("timeout_seconds")
        admission = payload.get("admission")
        if not _valid_id(payload.get("session_id")) or not isinstance(admission, dict):
            return False
        if (
            not isinstance(argv, list)
            or not 1 <= len(argv) <= 64
            or any(
                not isinstance(arg, str)
                or not 1 <= len(arg) <= 4096
                or any(
                    ord(char) < 0x20 and char not in "\t"
                    or ord(char) == 0x7F
                    for char in arg
                )
                for arg in argv
            )
            or sum(len(arg.encode("utf-8")) for arg in argv) > 16 * 1024
        ):
            return False
        if (
            not isinstance(timeout, int | float)
            or isinstance(timeout, bool)
            or not math.isfinite(float(timeout))
            or not 0.1 <= float(timeout) <= 600.0
        ):
            return False
        return True

    if path == "/v1/session/resolve-port":
        return (
            _exact_keys(
                payload,
                {
                    "schema",
                    "request_id",
                    "session_id",
                    "port",
                },
            )
            and _valid_id(payload.get("session_id"))
            and _valid_port(payload.get("port"))
        )

    if path == "/v1/session/verification-status":
        return (
            _exact_keys(
                payload,
                {
                    "schema", "request_id", "session_id",
                    "contract_hash", "manifest_digest", "file_path",
                },
            )
            and _valid_id(payload.get("session_id"))
            and _valid_digest(payload.get("contract_hash"))
            and _valid_digest(payload.get("manifest_digest"))
            and (
                payload.get("file_path") is None
                or _plan_path(payload.get("file_path"))
            )
        )

    if path == "/v1/session/release-status":
        return (
            _exact_keys(
                payload,
                {
                    "schema", "request_id", "session_id",
                    "release_request_id", "contract_hash", "manifest_digest",
                },
            )
            and _valid_id(payload.get("session_id"))
            and _valid_id(payload.get("release_request_id"))
            and _valid_digest(payload.get("contract_hash"))
            and _valid_digest(payload.get("manifest_digest"))
        )

    if path == "/v1/session/preparation-status":
        return (
            _exact_keys(
                payload,
                {
                    "schema", "request_id", "preparation_request_id",
                    "contract_hash", "manifest_digest",
                },
            )
            and _valid_id(payload.get("preparation_request_id"))
            and _valid_digest(payload.get("contract_hash"))
            and _valid_digest(payload.get("manifest_digest"))
        )

    if path == "/v1/session/file-chunk":
        return (
            _exact_keys(
                payload,
                {
                    "schema", "request_id", "session_id", "contract_hash",
                    "manifest_digest", "file_path", "content_sha256",
                    "offset", "chunk_base64", "final",
                },
            )
            and _valid_id(payload.get("session_id"))
            and _valid_digest(payload.get("contract_hash"))
            and _valid_digest(payload.get("manifest_digest"))
            and _plan_path(payload.get("file_path"))
            and _valid_digest(payload.get("content_sha256"))
            and _plan_count(payload.get("offset"), 1024 * 1024)
            and isinstance(payload.get("chunk_base64"), str)
            and len(payload["chunk_base64"]) <= (
                (RUNNER_RPC_MAX_FILE_CHUNK_BYTES + 2) // 3
            ) * 4
            and type(payload.get("final")) is bool
        )

    if path == "/v1/session/plan-receipt":
        return (
            _exact_keys(
                payload,
                {
                    "schema", "request_id", "session_id",
                    "contract_hash", "manifest_digest", "plan_json",
                },
            )
            and _valid_id(payload.get("session_id"))
            and _valid_digest(payload.get("contract_hash"))
            and _valid_digest(payload.get("manifest_digest"))
            and isinstance(payload.get("plan_json"), str)
            and len(payload["plan_json"]) <= 256 * 1024
        )

    if path == "/v1/session/release":
        return (
            _exact_keys(
                payload,
                {
                    "schema",
                    "request_id",
                    "session_id",
                    "contract_hash",
                },
            )
            and _valid_id(payload.get("session_id"))
            and _valid_digest(payload.get("contract_hash"))
        )

    if path == "/v1/session/delete":
        return (
            _exact_keys(
                payload,
                {
                    "schema",
                    "request_id",
                    "session_id",
                },
            )
            and _valid_id(payload.get("session_id"))
        )

    return False


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        *args: Any,
        max_concurrent_connections: int = RUNNER_RPC_MAX_CONCURRENT_CONNECTIONS,
        **kwargs: Any,
    ) -> None:
        if max_concurrent_connections < 1:
            raise ValueError("max_concurrent_connections must be positive")
        super().__init__(*args, **kwargs)
        self._request_slots = threading.BoundedSemaphore(
            max_concurrent_connections
        )

    def process_request(
        self,
        request: Any,
        client_address: Any,
    ) -> None:
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(
        self,
        request: Any,
        client_address: Any,
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class _RunnerRpcHttpHandler(BaseHTTPRequestHandler):
    server_version = "xbow-strix-runner-rpc/1"

    def setup(self) -> None:
        configure_runner_rpc_socket(self.request)
        self._read_deadline_timer: threading.Timer | None = None
        self._start_read_deadline()
        try:
            super().setup()
        except BaseException:
            self._cancel_read_deadline()
            raise

    def finish(self) -> None:
        self._cancel_read_deadline()
        super().finish()

    def _start_read_deadline(self) -> None:
        timer = threading.Timer(
            RUNNER_RPC_READ_DEADLINE_SECONDS,
            self._expire_read_deadline,
        )
        timer.daemon = True
        self._read_deadline_timer = timer
        timer.start()

    def _cancel_read_deadline(self) -> None:
        timer = getattr(self, "_read_deadline_timer", None)
        if timer is None:
            return
        timer.cancel()
        self._read_deadline_timer = None

    def _expire_read_deadline(self) -> None:
        with contextlib.suppress(OSError):
            self.request.shutdown(socket.SHUT_RDWR)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def _dispatch(self) -> None:
        service = getattr(self.server, "rpc_service", None)
        if not isinstance(service, RunnerRpcService):
            self._cancel_read_deadline()
            self._write(_error(503, "rpc_service_unavailable"))
            return

        body = b""
        if self.command == "POST":
            if self.headers.get("Transfer-Encoding"):
                self._cancel_read_deadline()
                self._write(_error(400, "invalid_request"))
                return
            length_raw = self.headers.get("Content-Length")
            try:
                length = int(length_raw or "0")
            except ValueError:
                self._cancel_read_deadline()
                self._write(_error(400, "invalid_request"))
                return
            if length < 0:
                self._cancel_read_deadline()
                self._write(_error(400, "invalid_request"))
                return
            if length > RUNNER_RPC_MAX_BODY_BYTES:
                self._cancel_read_deadline()
                self._write(_error(413, "request_too_large"))
                return
            body = self.rfile.read(length)
            if len(body) != length:
                self._cancel_read_deadline()
                self._write(_error(400, "invalid_request"))
                return

        self._cancel_read_deadline()
        result = service.handle(
            method=self.command,
            path=self.path,
            headers={key: value for key, value in self.headers.items()},
            body=body,
        )
        self._write(
            result,
            request_body=body,
            response_secret=(
                service._secret
                if self.command == "POST"
                and self.path in _MUTATION_PATHS
                and result.status in (200, 201)
                else None
            ),
        )

    def _write(
        self,
        result: RunnerRpcResponse,
        *,
        request_body: bytes = b"",
        response_secret: str | None = None,
    ) -> None:
        payload = json.dumps(
            result.json_body,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(result.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if response_secret is not None:
            self.send_header(
                "X-Xbow-Runner-Response-Signature",
                sign_runner_rpc_response(
                    method=self.command,
                    path=self.path,
                    request_body=request_body,
                    response_body=payload,
                    status=result.status,
                    secret=response_secret,
                    timestamp=int(self.headers["X-Xbow-Runner-Timestamp"]),
                    nonce=self.headers["X-Xbow-Runner-Nonce"],
                ),
            )
        for name, value in result.headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _rpc_secret_from_env() -> str | None:
    secret = os.getenv("XBOW_STRIX_RUNNER_RPC_HMAC_KEY", "")
    if not secret:
        return None
    try:
        _runner_rpc_secret_bytes(secret)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    return secret


def _admission_secret_from_env() -> str | None:
    secret = os.getenv("XBOW_STRIX_RUNNER_ADMISSION_HMAC_KEY", "")
    if not secret:
        return None
    try:
        validate_strix_runner_exec_ticket_secret(secret)
        validate_strix_runner_manifest_ticket_secret(secret)
    except (StrixRunnerExecTicketError, StrixRunnerManifestTicketError) as exc:
        raise RuntimeError(str(exc)) from exc
    return secret


def serve() -> None:
    attestation = attest_strix_runner()
    if attestation.get("active_execution_enabled") is not False:
        raise RuntimeError("Strix runner attestation did not fail closed")

    service = RunnerRpcService(
        secret=_rpc_secret_from_env(),
        admission_secret=_admission_secret_from_env(),
        active_execution=False,
        replay_db_path=RUNNER_RPC_REPLAY_DB_PATH,
    )
    server = BoundedThreadingHTTPServer(
        ("0.0.0.0", RUNNER_RPC_PORT),
        _RunnerRpcHttpHandler,
    )
    server.daemon_threads = True
    setattr(server, "rpc_service", service)
    server.serve_forever(poll_interval=0.5)


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if not args.serve:
        raise RuntimeError("only --serve is supported")
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
