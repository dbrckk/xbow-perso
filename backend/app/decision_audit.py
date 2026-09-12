from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from .observation_graph import ObservationGraph


_AUDIT_FIELDS = {
    "action",
    "agent",
    "reason",
    "priority",
    "graph_fingerprint",
    "audit_seq",
    "previous_decision_hash",
}


def _canonical_decision_payload(
    observation_id: str,
    metadata: dict[str, Any],
) -> bytes:
    payload = {
        "id": observation_id,
        **{key: metadata.get(key) for key in sorted(_AUDIT_FIELDS)},
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def seal_decision_metadata(
    observation_id: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    sealed = dict(metadata)
    canonical = _canonical_decision_payload(observation_id, sealed)
    sealed["decision_hash"] = hashlib.sha256(canonical).hexdigest()

    secret = os.getenv("XBOW_AUDIT_HMAC_KEY")
    if secret:
        sealed["decision_signature_alg"] = "hmac-sha256"
        sealed["decision_signature"] = hmac.new(
            secret.encode("utf-8"),
            canonical,
            hashlib.sha256,
        ).hexdigest()
    else:
        sealed["decision_signature_alg"] = None
        sealed["decision_signature"] = None
    return sealed


def _planner_decisions(graph: ObservationGraph):
    return [
        item
        for item in graph.by_kind("evidence")
        if item.metadata.get("memory_type") == "planner_decision"
    ]


def next_audit_link(graph: ObservationGraph) -> tuple[int, str | None]:
    sealed = [
        item
        for item in _planner_decisions(graph)
        if isinstance(item.metadata.get("audit_seq"), int)
        and item.metadata.get("decision_hash")
    ]
    if not sealed:
        return 1, None
    latest = max(sealed, key=lambda item: int(item.metadata["audit_seq"]))
    return int(latest.metadata["audit_seq"]) + 1, str(latest.metadata["decision_hash"])


def verify_decision_audit_chain(graph: ObservationGraph) -> dict[str, Any]:
    decisions = _planner_decisions(graph)
    legacy = [
        item.id
        for item in decisions
        if not isinstance(item.metadata.get("audit_seq"), int)
        or not item.metadata.get("decision_hash")
    ]
    sealed = [
        item
        for item in decisions
        if isinstance(item.metadata.get("audit_seq"), int)
        and item.metadata.get("decision_hash")
    ]
    sealed.sort(key=lambda item: int(item.metadata["audit_seq"]))

    expected_seq = 1
    previous_hash: str | None = None
    checked = 0
    for item in sealed:
        metadata = item.metadata
        seq = int(metadata["audit_seq"])
        if seq != expected_seq:
            return {
                "valid": False,
                "checked": checked,
                "sealed_decisions": len(sealed),
                "legacy_unsealed": legacy,
                "reason": "decision audit sequence gap",
            }
        if metadata.get("previous_decision_hash") != previous_hash:
            return {
                "valid": False,
                "checked": checked,
                "sealed_decisions": len(sealed),
                "legacy_unsealed": legacy,
                "reason": "previous decision hash mismatch",
            }

        canonical = _canonical_decision_payload(item.id, metadata)
        actual_hash = hashlib.sha256(canonical).hexdigest()
        if not hmac.compare_digest(str(metadata.get("decision_hash")), actual_hash):
            return {
                "valid": False,
                "checked": checked,
                "sealed_decisions": len(sealed),
                "legacy_unsealed": legacy,
                "reason": "decision hash mismatch",
            }

        signature = metadata.get("decision_signature")
        if signature is not None:
            if metadata.get("decision_signature_alg") != "hmac-sha256":
                return {
                    "valid": False,
                    "checked": checked,
                    "sealed_decisions": len(sealed),
                    "legacy_unsealed": legacy,
                    "reason": "unsupported decision signature algorithm",
                }
            secret = os.getenv("XBOW_AUDIT_HMAC_KEY")
            if not secret:
                return {
                    "valid": False,
                    "checked": checked,
                    "sealed_decisions": len(sealed),
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
                    "sealed_decisions": len(sealed),
                    "legacy_unsealed": legacy,
                    "reason": "decision signature mismatch",
                }

        previous_hash = str(metadata["decision_hash"])
        expected_seq += 1
        checked += 1

    return {
        "valid": True,
        "checked": checked,
        "sealed_decisions": len(sealed),
        "legacy_unsealed": legacy,
        "reason": None,
    }
