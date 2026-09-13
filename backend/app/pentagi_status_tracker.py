from __future__ import annotations

import json
from dataclasses import dataclass

from .pentagi_flow_status import PentagiFlowStatus, fetch_pentagi_flow_status


class PentagiStatusTrackingError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiStatusSnapshot:
    campaign_id: str
    flow_id: str
    status: str
    artifact: dict


def refresh_pentagi_flow_status(
    store,
    campaign_id: str,
    receipt_artifact_id: str,
    *,
    timeout_seconds: float | None = None,
) -> PentagiStatusSnapshot:
    """Refresh one known PentAGI flow from its durable creation receipt."""

    metadata, content = store.read_artifact(campaign_id, receipt_artifact_id)
    if metadata.get("kind") != "pentagi_receipt":
        raise PentagiStatusTrackingError("artifact is not a PentAGI receipt")
    try:
        receipt = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PentagiStatusTrackingError("PentAGI receipt is invalid JSON") from exc
    if not isinstance(receipt, dict):
        raise PentagiStatusTrackingError("PentAGI receipt must be an object")

    flow_id = receipt.get("flow_id")
    endpoint = receipt.get("endpoint")
    idempotency_key = receipt.get("idempotency_key")
    if not all(isinstance(value, str) and value for value in (flow_id, endpoint, idempotency_key)):
        raise PentagiStatusTrackingError("PentAGI receipt metadata is incomplete")

    remote: PentagiFlowStatus = fetch_pentagi_flow_status(
        endpoint,
        flow_id,
        timeout_seconds=timeout_seconds,
    )
    snapshot = {
        "flow_id": remote.flow_id,
        "status": remote.status,
        "title": remote.title,
        "source_receipt_id": receipt_artifact_id,
    }
    artifact = store.put_artifact(
        campaign_id,
        "pentagi_status",
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        media_type="application/json",
        idempotency_key=f"{idempotency_key}:status:{remote.status}",
    )
    return PentagiStatusSnapshot(
        campaign_id=campaign_id,
        flow_id=remote.flow_id,
        status=remote.status,
        artifact=artifact,
    )
