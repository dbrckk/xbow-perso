from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any
from uuid import uuid4

import redis

from .jobqueue import _bounded_identifier, _job_lease_seconds, _max_job_payload_bytes, utcnow

_ALLOWED_KINDS = {"strix_scan", "independent_validation", "browser_flow", "recon_task", "report"}
_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


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

    def _job_key(self, job_id: str) -> str:
        return f"{self.prefix}:job:{job_id}"

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
                pipe.zadd(self._queued, {job_id: score})
                pipe.sadd(self._all, job_id)
                pipe.sadd(self._campaign_key(campaign_id), job_id)
                pipe.execute()
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
                    pipe.zadd(self._queued, {job_id: score})
                    pipe.sadd(self._all, job_id)
                    pipe.sadd(self._campaign_key(campaign_id), job_id)
                    pipe.hset(dedupe_hash, dedupe_key, job_id)
                    pipe.execute()
                    break
            except redis.WatchError:
                continue

        created = self.get(job_id)
        if created is None:
            raise RuntimeError("queued job disappeared")
        return created

    def get(self, job_id: str) -> dict[str, Any] | None:
        job_id = _bounded_identifier(job_id, "job_id")
        return self._decode(self.redis.hgetall(self._job_key(job_id)))

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
        return {"total": len(ids), "by_status": counts, "oldest_queued_at": oldest_at}

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
                        pipe.execute()
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
                            pipe.zadd(self._queued, {job_id: time.time()})
                        pipe.execute()
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
                        pipe.execute()
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
                    pipe.zadd(self._running, {job_id: score})
                    pipe.execute()
                    return self.get(job_id)
            except redis.WatchError:
                continue

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
                        pipe.zadd(self._queued, {job_id: time.time()})
                    pipe.execute()
                    return self.get(job_id)
            except redis.WatchError:
                continue
