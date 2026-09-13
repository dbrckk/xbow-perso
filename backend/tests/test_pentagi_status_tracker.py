import json

import pytest

from app.pentagi_flow_status import PentagiFlowStatus
from app.pentagi_status_tracker import (
    PentagiStatusTrackingError,
    refresh_pentagi_flow_status,
)


class _Store:
    def __init__(self, receipt_kind="pentagi_receipt"):
        self.receipt_kind = receipt_kind
        self.writes = []

    def read_artifact(self, campaign_id, artifact_id):
        return (
            {"kind": self.receipt_kind},
            json.dumps(
                {
                    "flow_id": "flow-42",
                    "endpoint": "https://pentagi.example.test/api/v1/graphql",
                    "idempotency_key": "pentagi:abc",
                }
            ).encode(),
        )

    def put_artifact(self, campaign_id, kind, content, **kwargs):
        record = {
            "campaign_id": campaign_id,
            "kind": kind,
            "content": content,
            **kwargs,
        }
        self.writes.append(record)
        return record


def test_refresh_persists_idempotent_status_snapshot(monkeypatch):
    store = _Store()
    monkeypatch.setattr(
        "app.pentagi_status_tracker.fetch_pentagi_flow_status",
        lambda endpoint, flow_id, **kwargs: PentagiFlowStatus(
            flow_id="flow-42",
            status="running",
            title="scan",
            body={"id": "flow-42", "status": "running"},
        ),
    )

    result = refresh_pentagi_flow_status(store, "campaign-1", "receipt-1")

    assert result.status == "running"
    assert result.flow_id == "flow-42"
    assert len(store.writes) == 1
    write = store.writes[0]
    assert write["kind"] == "pentagi_status"
    assert write["idempotency_key"] == "pentagi:abc:status:running"
    decoded = json.loads(write["content"].decode())
    assert decoded == {
        "flow_id": "flow-42",
        "source_receipt_id": "receipt-1",
        "status": "running",
        "title": "scan",
    }


def test_refresh_rejects_non_receipt_artifact(monkeypatch):
    store = _Store(receipt_kind="report")
    with pytest.raises(PentagiStatusTrackingError, match="not a PentAGI receipt"):
        refresh_pentagi_flow_status(store, "campaign-1", "artifact-1")
