from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from .secret_vault import SecretVaultError, resolve_secret

_VOLATILE_FIELDS = {"event_hash", "event_signature", "event_signature_alg"}


def _canonical_event(event: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in event.items() if key not in _VOLATILE_FIELDS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def seal_campaign_event(event: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    sealed = dict(event)
    previous = events[-1].get("event_hash") if events else None
    sealed["event_seq"] = len(events) + 1
    sealed["previous_event_hash"] = previous
    canonical = _canonical_event(sealed)
    sealed["event_hash"] = hashlib.sha256(canonical).hexdigest()
    try:
        secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
    except SecretVaultError as exc:
        raise RuntimeError("campaign audit signing configuration is invalid") from exc
    if secret:
        sealed["event_signature_alg"] = "hmac-sha256"
        sealed["event_signature"] = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    else:
        sealed["event_signature_alg"] = None
        sealed["event_signature"] = None
    return sealed


def append_campaign_event(events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    events.append(seal_campaign_event(event, events))


def verify_campaign_event_chain(events: list[dict[str, Any]]) -> dict[str, Any]:
    # Backward compatibility: historical events remain explicitly reported as legacy.
    first_sealed = next((i for i, item in enumerate(events) if item.get("event_hash")), len(events))
    legacy = first_sealed
    previous = events[first_sealed - 1].get("event_hash") if first_sealed else None
    checked = 0
    expected_seq = first_sealed + 1
    for item in events[first_sealed:]:
        if item.get("event_seq") != expected_seq:
            return {"valid": False, "checked": checked, "legacy_unsealed": legacy, "reason": "campaign event sequence gap"}
        if item.get("previous_event_hash") != previous:
            return {"valid": False, "checked": checked, "legacy_unsealed": legacy, "reason": "previous campaign event hash mismatch"}
        canonical = _canonical_event(item)
        digest = hashlib.sha256(canonical).hexdigest()
        if not hmac.compare_digest(str(item.get("event_hash")), digest):
            return {"valid": False, "checked": checked, "legacy_unsealed": legacy, "reason": "campaign event hash mismatch"}
        signature = item.get("event_signature")
        if signature is not None:
            if item.get("event_signature_alg") != "hmac-sha256":
                return {"valid": False, "checked": checked, "legacy_unsealed": legacy, "reason": "unsupported campaign event signature algorithm"}
            try:
                secret = resolve_secret("audit_hmac_key", "XBOW_AUDIT_HMAC_KEY")
            except SecretVaultError:
                secret = None
            if not secret:
                return {"valid": False, "checked": checked, "legacy_unsealed": legacy, "reason": "verification key unavailable"}
            expected = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(str(signature), expected):
                return {"valid": False, "checked": checked, "legacy_unsealed": legacy, "reason": "campaign event signature mismatch"}
        previous = digest
        expected_seq += 1
        checked += 1
    return {"valid": True, "checked": checked, "legacy_unsealed": legacy, "reason": None}
