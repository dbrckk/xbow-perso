from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any
from uuid import uuid4

import redis

from .jobqueue import _bounded_identifier, _job_lease_seconds, _max_job_payload_bytes, utcnow
from .queue_audit import build_transition_event, verify_transition_events
from .queue_recovery import analyze_queue_recovery

_ALLOWED_KINDS = {"strix_scan", "nuclei_scan", "independent_validation", "browser_flow", "recon_task", "report", "pentagi_flow", "pentagi_status"}
_STATUSES = ("queued", "running", "completed", "failed", "cancelled")
_DEDICATED_KINDS = {"pentagi_flow", "pentagi_status"}


def _uses_generic_queue(kind: str) -> bool:
    return kind not in _DEDICATED_KINDS


class RedisJobQueue:
    """Redis-backed durable queue with ownership, leases, retries and deduplication."""

    def __init__(self, url: str | None = None):
        self.url = (url or os.getenv("XBOW_REDIS_URL") or "").strip()
        if not self.url:
            raise ValueError("XBOW_REDIS_URL is required for Redis queue")
        if not self.url.startswith(("redis://", "rediss://")):
            raise ValueError("XBOW_REDIS_URL must be a Redis URL")
        self.prefix = (os.getenv("XBOW_REDIS_PREFIX", "xbow:queue") or "").strip()
        if not self.prefix or len(self.prefix) > 100 or any(ord(ch) < 33 or ord(ch) == 127 for ch in self.prefix):
            raise ValueError("XBOW_REDIS_PREFIX is invalid")
        self.redis = redis.Redis.from_url(
            self.url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )

    @property
    def _queued(self) -> str:
        return f"{self.prefix}:queued"

    @property
    def _running(self) -> str:
        return f"{self.prefix}:running"

    @property
    def _all(self) -> str:
        return f"{self.prefix}:all"

    def _queued_kind(self, kind: str) -> str:
        digest = hashlib.sha256(kind.encode("utf-8")).hexdigest()[:24]
        return f"{self.prefix}:queued-kind:{digest}"

    def _job_key(self, job_id: str) -> str:
        return f"{self.prefix}:job:{job_id}"

    def _audit_key(self, job_id: str) -> str:
        return f"{self.prefix}:audit:{job_id}"

    def _append_transition(
        self,
        row: dict[str, Any],
        *,
        from_status: str | None,
        to_status: str,
        actor: str,
        reason: str,
        at: str,
    ) -> dict[str, Any]:
        job_id = str(row["id"])
        raw = self.redis.lindex(self._audit_key(job_id), -1)
        previous = json.loads(raw) if raw else None
        seq = int(previous["seq"]) + 1 if previous else 1
        previous_hash = str(previous["event_hash"]) if previous else None
        if previous and previous.get("to_status") != from_status:
            raise RuntimeError("queue transition audit status discontinuity")
        event = build_transition_event(
            job_id=job_id,
            campaign_id=str(row["campaign_id"]),
            kind=str(row["kind"]),
            seq=seq,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            reason=reason,
            at=at,
            previous_hash=previous_hash,
        )
        self.redis.rpush(
            self._audit_key(job_id),
            json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )
        return event

    def job_transitions(self, job_id: str) -> list[dict[str, Any]]:
        job_id = _bounded_identifier(job_id, "job_id")
        rows = self.redis.lrange(self._audit_key(job_id), 0, -1)
        return [json.loads(row) for row in rows]

    def verify_job_transitions(self, job_id: str) -> dict[str, Any]:
        events = self.job_transitions(job_id)
        verification = verify_transition_events(events)
        current = self.get(job_id)
        if current is None:
            return {**verification, "valid": False, "reason": "job missing"}
        if verification["valid"] and verification.get("final_status") != current["status"]:
            return {
                **verification,
                "valid": False,
                "reason": "audit final status does not match job status",
            }
        return verification

    def campaign_transition_audit(self, campaign_id: str) -> dict[str, Any]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        job_ids = sorted(self._campaign_members(campaign_id))
        invalid: list[dict[str, Any]] = []
        checked_events = 0
        for job_id in job_ids:
            result = self.verify_job_transitions(job_id)
            checked_events += int(result.get("checked", 0))
            if not result.get("valid"):
                invalid.append({"job_id": job_id, "reason": result.get("reason")})
        return {
            "campaign_id": campaign_id,
            "jobs": len(job_ids),
            "events": checked_events,
            "valid": not invalid,
            "invalid_jobs": invalid,
        }

    def _campaign_key(self, campaign_id: str) -> str:
        digest = hashlib.sha256(campaign_id.encode("utf-8")).hexdigest()
        return f"{self.prefix}:campaign:{digest}"

    def _dedupe_key(self, campaign_id: str, kind: str) -> str:
        digest = hashlib.sha256(f"{campaign_id}\0{kind}".encode("utf-8")).hexdigest()
        return f"{self.prefix}:dedupe:{digest}"

    @staticmethod
    def _decode(row: dict[str, str] | None) -> dict[str, Any] | None:
        if not row:
            return None
        result: dict[str, Any] = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["attempts"] = int(result["attempts"])
        result["max_attempts"] = int(result["max_attempts"])
        for key in ("claimed_by", "claimed_at", "last_error", "dedupe_key"):
            if result.get(key, "") == "":
                result[key] = None
        return result

    def recovery_assessment(self) -> dict[str, Any]:
        job_ids = sorted(self.redis.smembers(self._all))
        jobs: list[dict[str, Any]] = []
        audits: dict[str, dict[str, Any]] = {}
        for job_id in job_ids:
            job = self.get(str(job_id))
            if job is None:
                continue
            jobs.append(
                {
                    key: job.get(key)
                    for key in (
                        "id",
                        "campaign_id",
                        "kind",
                        "status",
                        "attempts",
                        "max_attempts",
                        "claimed_by",
                        "claimed_at",
                        "created_at",
                        "updated_at",
                    )
                }
            )
            audits[str(job_id)] = self.verify_job_transitions(str(job_id))
        return {
            **analyze_queue_recovery(
                jobs,
                lease_seconds=_job_lease_seconds(),
                audit_results=audits,
            ),
            "storage": "redis",
        }

    def health(self) -> dict[str, Any]:
        try:
            pong = bool(self.redis.ping())
        except redis.RedisError as exc:
            return {"ok": False, "storage": "redis", "error": exc.__class__.__name__}
        return {"ok": pong, "storage": "redis"}

    def enqueue(
        self,
        campaign_id: str,
        kind: str,
        payload: dict[str, Any],
        max_attempts: int = 2,
        *,
        dedupe_key: str | None = None,
    ) -> dict[str, Any]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        if kind not in _ALLOWED_KINDS:
            raise ValueError("unsupported job kind")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be 1..5")
        if dedupe_key is not None:
            dedupe_key = _bounded_identifier(dedupe_key, "dedupe_key")

        encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(encoded_payload.encode("utf-8")) > _max_job_payload_bytes():
            raise ValueError("job payload exceeds size limit")

        job_id = str(uuid4())
        now = utcnow()
        score = time.time()
        row = {
            "id": job_id,
            "campaign_id": campaign_id,
            "kind": kind,
            "payload": encoded_payload,
            "status": "queued",
            "attempts": "0",
            "max_attempts": str(max_attempts),
            "created_at": now,
            "updated_at": now,
            "claimed_by": "",
            "claimed_at": "",
            "last_error": "",
            "dedupe_key": dedupe_key or "",
        }

        if dedupe_key is None:
            with self.redis.pipeline(transaction=True) as pipe:
                pipe.hset(self._job_key(job_id), mapping=row)
                if _uses_generic_queue(kind):
                    pipe.zadd(self._queued, {job_id: score})
                pipe.zadd(self._queued_kind(kind), {job_id: score})
                pipe.sadd(self._all, job_id)
                pipe.sadd(self._campaign_key(campaign_id), job_id)
                pipe.execute()
            self._append_transition(
                row,
                from_status=None,
                to_status="queued",
                actor="queue",
                reason="job enqueued",
                at=now,
            )
            created = self.get(job_id)
            if created is None:
                raise RuntimeError("queued job disappeared")
            return created

        dedupe_hash = self._dedupe_key(campaign_id, kind)
        while True:
            try:
                with self.redis.pipeline() as pipe:
                    pipe.watch(dedupe_hash)
                    existing_id = pipe.hget(dedupe_hash, dedupe_key)
                    if existing_id:
                        pipe.unwatch()
                        existing = self.get(existing_id)
                        if existing is None:
                            raise RuntimeError("Redis queue dedupe index is inconsistent")
                        existing_payload = json.dumps(
                            existing["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
                        )
                        if existing_payload != encoded_payload:
                            raise ValueError("dedupe_key reused with different job payload")
                        return existing
                    pipe.multi()
                    pipe.hset(self._job_key(job_id), mapping=row)
                    if _uses_generic_queue(kind):
                        pipe.zadd(self._queued, {job_id: score})
                    pipe.zadd(self._queued_kind(kind), {job_id: score})
                    pipe.sadd(self._all, job_id)
                    pipe.sadd(self._campaign_key(campaign_id), job_id)
                    pipe.hset(dedupe_hash, dedupe_key, job_id)
                    pipe.execute()
                    break
            except redis.WatchError:
                continue

        self._append_transition(
            row,
            from_status=None,
            to_status="queued",
            actor="queue",
            reason="job enqueued",
            at=now,
        )
        created = self.get(job_id)
        if created is None:
            raise RuntimeError("queued job disappeared")
        return created

    def get(self, job_id: str) -> dict[str, Any] | None:
        job_id = _bounded_identifier(job_id, "job_id")
        return self._decode(self.redis.hgetall(self._job_key(job_id)))

    def get_by_dedupe(
        self,
        campaign_id: str,
        kind: str,
        dedupe_key: str,
    ) -> dict[str, Any] | None:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        kind = _bounded_identifier(kind, "kind")
        dedupe_key = _bounded_identifier(dedupe_key, "dedupe_key")
        job_id = self.redis.hget(self._dedupe_key(campaign_id, kind), dedupe_key)
        if not job_id:
            return None
        job = self.get(job_id)
        if job is None:
            raise RuntimeError("Redis queue dedupe index is inconsistent")
        return job

    def stats(self) -> dict[str, Any]:
        ids = list(self.redis.smembers(self._all))
        counts = {status: 0 for status in _STATUSES}
        if ids:
            with self.redis.pipeline(transaction=False) as pipe:
                for job_id in ids:
                    pipe.hget(self._job_key(job_id), "status")
                statuses = pipe.execute()
            for status in statuses:
                if status in counts:
                    counts[status] += 1

        oldest_at = None
        oldest_ids = self.redis.zrange(self._queued, 0, 0)
        if oldest_ids:
            oldest_at = self.redis.hget(self._job_key(oldest_ids[0]), "created_at")

        oldest_running_at = None
        oldest_running_ids = self.redis.zrange(self._running, 0, 0)
        if oldest_running_ids:
            oldest_running_at = self.redis.hget(
                self._job_key(oldest_running_ids[0]),
                "claimed_at",
            )

        return {
            "total": len(ids),
            "by_status": counts,
            "oldest_queued_at": oldest_at,
            "oldest_running_claimed_at": oldest_running_at,
        }

    def _campaign_members(self, campaign_id: str) -> list[str]:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        return list(self.redis.smembers(self._campaign_key(campaign_id)))

    def campaign_job_counts(self, campaign_id: str) -> dict[str, int]:
        members = self._campaign_members(campaign_id)
        counts = {kind: 0 for kind in _ALLOWED_KINDS}
        if not members:
            return counts
        with self.redis.pipeline(transaction=False) as pipe:
            for job_id in members:
                pipe.hget(self._job_key(job_id), "kind")
            kinds = pipe.execute()
        for kind in kinds:
            if kind in counts:
                counts[kind] += 1
        return counts

    def campaign_job_status_counts(self, campaign_id: str) -> dict[str, int]:
        members = self._campaign_members(campaign_id)
        counts = {status: 0 for status in _STATUSES}
        if not members:
            return counts
        with self.redis.pipeline(transaction=False) as pipe:
            for job_id in members:
                pipe.hget(self._job_key(job_id), "status")
            statuses = pipe.execute()
        for status in statuses:
            if status in counts:
                counts[status] += 1
        return counts

    def cancel_queued(self, campaign_id: str) -> int:
        campaign_id = _bounded_identifier(campaign_id, "campaign_id")
        count = 0
        for job_id in list(self.redis.smembers(self._campaign_key(campaign_id))):
            key = self._job_key(job_id)
            while True:
                try:
                    with self.redis.pipeline() as pipe:
                        pipe.watch(key, self._queued)
                        row = pipe.hgetall(key)
                        if not row or row.get("status") != "queued" or row.get("campaign_id") != campaign_id:
                            pipe.unwatch()
                            break
                        now = utcnow()
                        pipe.multi()
                        pipe.hset(
                            key,
                            mapping={
                                "status": "cancelled",
                                "updated_at": now,
                                "claimed_by": "",
                                "claimed_at": "",
                                "last_error": "campaign cancelled before execution",
                            },
                        )
                        pipe.zrem(self._queued, job_id)
                        pipe.zrem(self._queued_kind(row.get("kind", "")), job_id)
                        pipe.execute()
                        self._append_transition(
                            row,
                            from_status="queued",
                            to_status="cancelled",
                            actor="campaign-control",
                            reason="campaign cancelled before execution",
                            at=now,
                        )
                        count += 1
                        break
                except redis.WatchError:
                    continue
        return count

    def cancel_owned(self, job_id: str, worker_id: str, reason: str = "campaign cancelled") -> dict[str, Any] | None:
        job_id = _bounded_identifier(job_id, "job_id")
        worker_id = _bounded_identifier(worker_id, "worker_id")
        reason = reason.strip()
        if len(reason) > 4000:
            reason = reason[-4000:]
        if any(ord(ch) < 32 and ch not in "\t" for ch in reason):
            raise ValueError("cancel reason contains invalid characters")

        key = self._job_key(job_id)
        while True:
            try:
                with self.redis.pipeline() as pipe:
                    pipe.watch(key, self._running)
                    row = pipe.hgetall(key)
                    if not row or row.get("status") != "running" or row.get("claimed_by") != worker_id:
                        pipe.unwatch()
                        return None
                    pipe.multi()
                    pipe.hset(
                        key,
                        mapping={
                            "status": "cancelled",
                            "updated_at": utcnow(),
                            "last_error": reason[-4000:] if reason else "",
                            "claimed_by": "",
                            "claimed_at": "",
                        },
                    )
                    pipe.zrem(self._running, job_id)
                    pipe.execute()
                    self._append_transition(
                        row,
                        from_status="running",
                        to_status="cancelled",
                        actor=worker_id,
                        reason=reason or "campaign cancelled",
                        at=utcnow(),
                    )
                    return self.get(job_id)
            except redis.WatchError:
                continue

    def recover_expired_leases(self) -> int:
        lease_seconds = _job_lease_seconds()
        cutoff = time.time() - lease_seconds
        stale_ids = list(self.redis.zrangebyscore(self._running, "-inf", cutoff))
        recovered = 0
        for job_id in stale_ids:
            key = self._job_key(job_id)
            while True:
                try:
                    with self.redis.pipeline() as pipe:
                        pipe.watch(key, self._running, self._queued)
                        row = pipe.hgetall(key)
                        score = pipe.zscore(self._running, job_id)
                        if not row or row.get("status") != "running" or score is None or score > cutoff:
                            pipe.unwatch()
                            break
                        exhausted = int(row["attempts"]) >= int(row["max_attempts"])
                        status = "failed" if exhausted else "queued"
                        now = utcnow()
                        pipe.multi()
                        pipe.hset(
                            key,
                            mapping={
                                "status": status,
                                "updated_at": now,
                                "claimed_by": "",
                                "claimed_at": "",
                                "last_error": "worker lease expired before completion",
                            },
                        )
                        pipe.zrem(self._running, job_id)
                        if status == "queued":
                            if _uses_generic_queue(row.get("kind", "")):
                                pipe.zadd(self._queued, {job_id: time.time()})
                            pipe.zadd(self._queued_kind(row.get("kind", "")), {job_id: time.time()})
                        pipe.execute()
                        self._append_transition(
                            row,
                            from_status="running",
                            to_status=status,
                            actor="lease-recovery",
                            reason="worker lease expired before completion",
                            at=now,
                        )
                        recovered += 1
                        break
                except redis.WatchError:
                    continue
        return recovered

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        worker_id = _bounded_identifier(worker_id, "worker_id")
        self.recover_expired_leases()

        while True:
            try:
                with self.redis.pipeline() as pipe:
                    pipe.watch(self._queued)
                    ids = pipe.zrange(self._queued, 0, 0)
                    if not ids:
                        pipe.unwatch()
                        return None
                    job_id = ids[0]
                    key = self._job_key(job_id)
                    pipe.watch(key)
                    row = pipe.hgetall(key)
                    if not row:
                        pipe.multi()
                        pipe.zrem(self._queued, job_id)
                        pipe.execute()
                        continue
                    if row.get("status") != "queued":
                        pipe.multi()
                        pipe.zrem(self._queued, job_id)
                        pipe.zrem(self._queued_kind(row.get("kind", "")), job_id)
                        pipe.execute()
                        continue
                    if not _uses_generic_queue(row.get("kind", "")):
                        pipe.multi()
                        pipe.zrem(self._queued, job_id)
                        pipe.execute()
                        continue
                    if int(row["attempts"]) >= int(row["max_attempts"]):
                        pipe.multi()
                        pipe.hset(
                            key,
                            mapping={
                                "status": "failed",
                                "updated_at": utcnow(),
                                "last_error": row.get("last_error") or "retry budget exhausted",
                            },
                        )
                        pipe.zrem(self._queued, job_id)
                        pipe.zrem(self._queued_kind(row.get("kind", "")), job_id)
                        pipe.execute()
                        self._append_transition(
                            row,
                            from_status="queued",
                            to_status="failed",
                            actor="queue",
                            reason="retry budget exhausted",
                            at=utcnow(),
                        )
                        continue

                    now = utcnow()
                    score = time.time()
                    pipe.multi()
                    pipe.hset(
                        key,
                        mapping={
                            "status": "running",
                            "attempts": str(int(row["attempts"]) + 1),
                            "claimed_by": worker_id,
                            "claimed_at": now,
                            "updated_at": now,
                        },
                    )
                    pipe.zrem(self._queued, job_id)
                    pipe.zrem(self._queued_kind(row.get("kind", "")), job_id)
                    pipe.zadd(self._running, {job_id: score})
                    pipe.execute()
                    self._append_transition(
                        row,
                        from_status="queued",
                        to_status="running",
                        actor=worker_id,
                        reason="job claimed",
                        at=now,
                    )
                    return self.get(job_id)
            except redis.WatchError:
                continue


    def claim_allowed(self, worker_id: str, kinds: tuple[str, ...] | list[str]) -> dict[str, Any] | None:
        """Claim the oldest queued job across an explicit set of kinds."""
        worker_id = _bounded_identifier(worker_id, "worker_id")
        normalized = tuple(dict.fromkeys(_bounded_identifier(kind, "kind") for kind in kinds))
        if not normalized:
            raise ValueError("at least one allowed job kind is required")
        if any(kind not in _ALLOWED_KINDS for kind in normalized):
            raise ValueError("unsupported job kind")
        self.recover_expired_leases()

        for _ in range(32):
            candidates: list[tuple[float, str, str]] = []
            for kind in normalized:
                rows = self.redis.zrange(
                    self._queued_kind(kind),
                    0,
                    0,
                    withscores=True,
                )
                if rows:
                    job_id, score = rows[0]
                    candidates.append((float(score), str(job_id), kind))
            if not candidates:
                return None

            _score, _job_id, chosen_kind = min(candidates)
            claimed = self.claim_kind(worker_id, chosen_kind)
            if claimed is not None:
                return claimed
        return None


    def claim_kind(self, worker_id: str, kind: str) -> dict[str, Any] | None:
        """Atomically claim only one explicitly requested job kind."""
        worker_id = _bounded_identifier(worker_id, "worker_id")
        kind = _bounded_identifier(kind, "kind")
        if kind not in _ALLOWED_KINDS:
            raise ValueError("unsupported job kind")
        self.recover_expired_leases()

        queued_kind = self._queued_kind(kind)
        for job_id in self.redis.zrange(queued_kind, 0, -1):
            key = self._job_key(job_id)
            while True:
                try:
                    with self.redis.pipeline() as pipe:
                        pipe.watch(key, self._running, self._queued, queued_kind)
                        row = pipe.hgetall(key)
                        if (
                            not row
                            or row.get("status") != "queued"
                            or row.get("kind") != kind
                            or int(row["attempts"]) >= int(row["max_attempts"])
                        ):
                            pipe.multi()
                            pipe.zrem(queued_kind, job_id)
                            pipe.execute()
                            break
                        now = utcnow()
                        pipe.multi()
                        pipe.hset(
                            key,
                            mapping={
                                "status": "running",
                                "attempts": str(int(row["attempts"]) + 1),
                                "claimed_by": worker_id,
                                "claimed_at": now,
                                "updated_at": now,
                            },
                        )
                        pipe.zrem(self._queued, job_id)
                        pipe.zrem(queued_kind, job_id)
                        pipe.zadd(self._running, {job_id: time.time()})
                        pipe.execute()
                        self._append_transition(
                            row,
                            from_status="queued",
                            to_status="running",
                            actor=worker_id,
                            reason="job claimed",
                            at=now,
                        )
                        return self.get(job_id)
                except redis.WatchError:
                    continue
        return None

    def heartbeat(self, job_id: str, worker_id: str) -> bool:
        job_id = _bounded_identifier(job_id, "job_id")
        worker_id = _bounded_identifier(worker_id, "worker_id")
        key = self._job_key(job_id)
        while True:
            try:
                with self.redis.pipeline() as pipe:
                    pipe.watch(key, self._running)
                    row = pipe.hgetall(key)
                    if not row or row.get("status") != "running" or row.get("claimed_by") != worker_id:
                        pipe.unwatch()
                        return False
                    now = utcnow()
                    pipe.multi()
                    pipe.hset(key, mapping={"claimed_at": now, "updated_at": now})
                    pipe.zadd(self._running, {job_id: time.time()})
                    pipe.execute()
                    return True
            except redis.WatchError:
                continue

    def finish(
        self,
        job_id: str,
        worker_id: str,
        success: bool,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        job_id = _bounded_identifier(job_id, "job_id")
        worker_id = _bounded_identifier(worker_id, "worker_id")
        key = self._job_key(job_id)

        while True:
            try:
                with self.redis.pipeline() as pipe:
                    pipe.watch(key, self._running, self._queued)
                    row = pipe.hgetall(key)
                    if not row or row.get("status") != "running" or row.get("claimed_by") != worker_id:
                        pipe.unwatch()
                        return None
                    attempts = int(row["attempts"])
                    max_attempts = int(row["max_attempts"])
                    status = "completed" if success else ("queued" if attempts < max_attempts else "failed")
                    now = utcnow()
                    pipe.multi()
                    pipe.hset(
                        key,
                        mapping={
                            "status": status,
                            "updated_at": now,
                            "last_error": (error or "")[-4000:],
                            "claimed_by": "",
                            "claimed_at": "",
                        },
                    )
                    pipe.zrem(self._running, job_id)
                    if status == "queued":
                        if _uses_generic_queue(row.get("kind", "")):
                            pipe.zadd(self._queued, {job_id: time.time()})
                        pipe.zadd(self._queued_kind(row.get("kind", "")), {job_id: time.time()})
                    pipe.execute()
                    self._append_transition(
                        row,
                        from_status="running",
                        to_status=status,
                        actor=worker_id,
                        reason=(
                            "job completed"
                            if success
                            else ("job requeued after failure" if status == "queued" else "job failed")
                        ),
                        at=now,
                    )
                    return self.get(job_id)
            except redis.WatchError:
                continue
