from types import SimpleNamespace

from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.observation_graph import load_observation_graph
from app.storage import Storage
from app.recon_worker import ReconResult
from app.worker_service import (
    _record_artifact_observation,
    _record_finding_observation,
    process_recon_task,
)


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
    assert len(graph.by_kind("endpoint")) == 1
    endpoint_id = graph.by_kind("endpoint")[0].id
    asset_id = graph.by_kind("asset")[0].id
    assert graph.by_kind("endpoint")[0].parent_ids == (asset_id,)
    assert graph.by_kind("finding")[0].parent_ids == (endpoint_id,)
    assert graph.by_kind("validation")[0].parent_ids == (finding_observation_id,)
    assert graph.by_kind("evidence")[0].id == evidence_id
    assert graph.by_kind("evidence")[0].parent_ids == (validation_id,)



def test_recon_observed_primary_target_is_recorded_as_endpoint(tmp_path, monkeypatch):
    store = Storage(str(tmp_path / "recon.sqlite3"), str(tmp_path / "artifacts"))
    campaign = Campaign(
        id="recon-primary",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    store.save_campaign(campaign.model_dump(mode="json"))

    monkeypatch.setattr(
        "app.worker_service.execute_recon_task",
        lambda _campaign, _payload: ReconResult(
            status="observed",
            target="https://example.test/",
            http_status=200,
            requests_made=1,
            request_budget=1,
            coverage_complete=True,
        ),
    )

    process_recon_task(
        {
            "id": "recon-job",
            "campaign_id": campaign.id,
            "payload": {"kind": "crawl", "target": "https://example.test"},
        },
        store,
    )

    graph = load_observation_graph(store, campaign.id)
    endpoints = graph.by_kind("endpoint")
    assert len(endpoints) == 1
    assert endpoints[0].value == "https://example.test/"
    assert endpoints[0].source == "recon:crawl"
