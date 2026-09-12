from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from .secret_vault import resolve_secret

_AUDIT_FIELDS = {
    "type",
    "job_id",
    "job_kind",
    "success",
    "status",
    "attempts",
    "at",
    "audit_seq",
    "previous_worker_hash",
}


def _canonical_worker_event(event: dict[str, Any]) -> bytes:
    payload = {key: event.get(key) for key in sorted(_AUDIT_FIELDS)}
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def next_worker_audit_link(events: list[dict[str, Any]]) -> tuple[int, str | None]:
    sealed = [
        item for item in events
        if item.get("type") == "worker_outcome"
        and isinstance(item.get("audit_seq"), int)
        and item.get("worker_hash")
    ]
    if not sealed:
        return 1, None
    latest = max(sealed, key=lambda item: int(item["audit_seq"]))
    return int(latest["audit_seq"]) + 1, str(latest["worker_hash"])


def seal_worker_outcome_event(
    event: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    sealed = dict(event)
    seq, previous = next_worker_audit_link(events)
    sealed["audit_seq"] = seq
    sealed["previous_worker_hash"] = previous
    canonical = _canonical_worker_event(sealed)
    sealed["worker_hash"] = hashlib.sha256(canonical).hexdigest()

    secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
    if secret:
        sealed["worker_signature_alg"] = "hmac-sha256"
        sealed["worker_signature"] = hmac.new(
            secret.encode("utf-8"),
            canonical,
            hashlib.sha256,
        ).hexdigest()
    else:
        sealed["worker_signature_alg"] = None
        sealed["worker_signature"] = None
    return sealed


def verify_worker_audit_chain(events: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = [item for item in events if item.get("type") == "worker_outcome"]
    legacy = [
        str(item.get("job_id") or "")
        for item in outcomes
        if not isinstance(item.get("audit_seq"), int) or not item.get("worker_hash")
    ]
    sealed = [
        item for item in outcomes
        if isinstance(item.get("audit_seq"), int) and item.get("worker_hash")
    ]
    sealed.sort(key=lambda item: int(item["audit_seq"]))

    expected_seq = 1
    previous_hash: str | None = None
    checked = 0
    for item in sealed:
        if int(item["audit_seq"]) != expected_seq:
            return {
                "valid": False,
                "checked": checked,
                "sealed_outcomes": len(sealed),
                "legacy_unsealed": legacy,
                "reason": "worker audit sequence gap",
            }
        if item.get("previous_worker_hash") != previous_hash:
            return {
                "valid": False,
                "checked": checked,
                "sealed_outcomes": len(sealed),
                "legacy_unsealed": legacy,
                "reason": "previous worker hash mismatch",
            }

        canonical = _canonical_worker_event(item)
        actual_hash = hashlib.sha256(canonical).hexdigest()
        if not hmac.compare_digest(str(item.get("worker_hash")), actual_hash):
            return {
                "valid": False,
                "checked": checked,
                "sealed_outcomes": len(sealed),
                "legacy_unsealed": legacy,
                "reason": "worker outcome hash mismatch",
            }

        signature = item.get("worker_signature")
        if signature is not None:
            if item.get("worker_signature_alg") != "hmac-sha256":
                return {
                    "valid": False,
                    "checked": checked,
                    "sealed_outcomes": len(sealed),
                    "legacy_unsealed": legacy,
                    "reason": "unsupported worker signature algorithm",
                }
            secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
            if not secret:
                return {
                    "valid": False,
                    "checked": checked,
                    "sealed_outcomes": len(sealed),
                    "legacy_unsealed": legacy,
                    "reason": "verification key unavailable",
                }
            expected_signature = hmac.new(
                secret.encode("utf-8"),
                canonical,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(str(signature), expected_signature):
                return {
                    "valid": False,
                    "checked": checked,
                    "sealed_outcomes": len(sealed),
                    "legacy_unsealed": legacy,
                    "reason": "worker signature mismatch",
                }

        previous_hash = str(item["worker_hash"])
        expected_seq += 1
        checked += 1

    return {
        "valid": True,
        "checked": checked,
        "sealed_outcomes": len(sealed),
        "legacy_unsealed": legacy,
        "reason": None,
    }
