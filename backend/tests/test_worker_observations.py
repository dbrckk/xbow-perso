from types import SimpleNamespace

from app.main import Finding
from app.observation_graph import load_observation_graph
from app.storage import Storage
from app.worker_service import _record_artifact_observation, _record_finding_observation


def test_worker_observation_lineage_roundtrips(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign({"id": "c1", "state": "ready", "created_at": "x", "updated_at": "x"})
    campaign = SimpleNamespace(id="c1")
    finding = Finding(
        id="f1",
        title="Demo finding",
        severity="medium",
        asset="https://example.com",
        endpoint="/api",
        summary="demo",
        discovered_by="strix",
    )

    finding_observation_id = _record_finding_observation(store, campaign, finding)
    artifact = store.put_artifact(
        "c1",
        "validation",
        b"{}",
        media_type="application/json",
        finding_id="f1",
        idempotency_key="job-1:validation",
    )
    validation_id = _record_artifact_observation(
        store,
        campaign,
        artifact,
        source="independent-http-validator",
        parent_ids=(finding_observation_id,),
        kind="validation",
        value="observed",
        metadata={"finding_id": "f1"},
    )
    evidence_id = _record_artifact_observation(
        store,
        campaign,
        artifact,
        source="independent-http-validator",
        parent_ids=(validation_id,),
        metadata={"artifact_kind": "validation"},
    )

    graph = load_observation_graph(store, "c1")
    assert len(graph.by_kind("asset")) == 1
    assert graph.by_kind("finding")[0].parent_ids == (graph.by_kind("asset")[0].id,)
    assert graph.by_kind("validation")[0].parent_ids == (finding_observation_id,)
    assert graph.by_kind("evidence")[0].id == evidence_id
    assert graph.by_kind("evidence")[0].parent_ids == (validation_id,)
