from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any


_INTEGRITY_FIELDS = {"receipt_hash", "signature", "signature_alg", "integrity_mode"}


def canonical_policy_receipt(receipt: dict[str, Any]) -> bytes:
    payload = {
        key: value
        for key, value in receipt.items()
        if key not in _INTEGRITY_FIELDS
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def seal_policy_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(receipt)
    canonical = canonical_policy_receipt(sealed)
    sealed["receipt_hash"] = hashlib.sha256(canonical).hexdigest()

    secret = os.getenv("XBOW_AUDIT_HMAC_KEY")
    if secret:
        sealed["signature_alg"] = "hmac-sha256"
        sealed["signature"] = hmac.new(
            secret.encode("utf-8"),
            canonical,
            hashlib.sha256,
        ).hexdigest()
        sealed["integrity_mode"] = "hmac-sha256"
    else:
        sealed["signature_alg"] = None
        sealed["signature"] = None
        sealed["integrity_mode"] = "sha256"

    return sealed


def verify_policy_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    expected_hash = str(receipt.get("receipt_hash") or "")
    if not expected_hash:
        return {
            "valid": False,
            "hash_valid": False,
            "signature_valid": None,
            "integrity_mode": str(receipt.get("integrity_mode") or "unknown"),
            "reason": "receipt_hash missing",
        }

    canonical = canonical_policy_receipt(receipt)
    actual_hash = hashlib.sha256(canonical).hexdigest()
    hash_valid = hmac.compare_digest(expected_hash, actual_hash)

    signature = receipt.get("signature")
    algorithm = receipt.get("signature_alg")
    if signature is None:
        return {
            "valid": hash_valid,
            "hash_valid": hash_valid,
            "signature_valid": None,
            "integrity_mode": str(receipt.get("integrity_mode") or "sha256"),
            "reason": None if hash_valid else "receipt hash mismatch",
        }

    if algorithm != "hmac-sha256":
        return {
            "valid": False,
            "hash_valid": hash_valid,
            "signature_valid": False,
            "integrity_mode": str(receipt.get("integrity_mode") or "unknown"),
            "reason": "unsupported signature algorithm",
        }

    secret = os.getenv("XBOW_AUDIT_HMAC_KEY")
    if not secret:
        return {
            "valid": False,
            "hash_valid": hash_valid,
            "signature_valid": None,
            "integrity_mode": "hmac-sha256",
            "reason": "verification key unavailable",
        }

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()
    signature_valid = hmac.compare_digest(str(signature), expected_signature)
    return {
        "valid": bool(hash_valid and signature_valid),
        "hash_valid": hash_valid,
        "signature_valid": signature_valid,
        "integrity_mode": "hmac-sha256",
        "reason": None if hash_valid and signature_valid else "receipt integrity check failed",
    }
