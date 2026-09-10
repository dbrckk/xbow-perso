from app.attack_surface import build_attack_surface, campaign_attack_surface
from app.main import Campaign, ProgramRules, TargetInput
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def test_surface_classifies_scope_and_topology_without_network_calls():
    graph = ObservationGraph()
    graph.add(Observation("asset:in", "asset", "example.test", "recon"))
    graph.add(Observation("asset:out", "asset", "outside.test", "recon"))
    graph.add(
        Observation(
            "endpoint:in",
            "endpoint",
            "https://example.test/api?token=secret",
            "recon",
            parent_ids=("asset:in",),
        )
    )
    graph.add(
        Observation(
            "endpoint:out",
            "endpoint",
            "https://outside.test/public?id=42",
            "recon",
            parent_ids=("asset:out",),
        )
    )
    graph.add(
        Observation(
            "endpoint:mismatch",
            "endpoint",
            "https://example.test/mismatch",
            "browser",
            parent_ids=("asset:out",),
        )
    )
    graph.add(Observation("endpoint:orphan", "endpoint", "https://example.test/orphan", "browser"))

    result = build_attack_surface(graph, scope_checker=lambda host: host == "example.test")
    by_id = {item["id"]: item for item in result["endpoints"]}

    assert result["read_only"] is True
    assert result["summary"]["in_scope_asset_count"] == 1
    assert result["summary"]["out_of_scope_asset_count"] == 1
    assert result["summary"]["in_scope_endpoint_count"] == 3
    assert result["summary"]["out_of_scope_endpoint_count"] == 1
    assert result["summary"]["orphan_endpoint_count"] == 1
    assert result["summary"]["host_asset_mismatch_count"] == 1
    assert by_id["endpoint:mismatch"]["host_asset_mismatch"] is True
    assert by_id["endpoint:orphan"]["asset_parent_ids"] == []
    assert "secret" not in str(result)
    assert "42" not in str(result)


def test_surface_route_uses_campaign_scope_rules(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="scope-surface",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["*.example.test", "example.test"],
                denied_targets=["blocked.example.test"],
            ),
        ),
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    store.put_observation(campaign.id, Observation("asset:root", "asset", "example.test", "recon").to_dict())
    store.put_observation(campaign.id, Observation("asset:blocked", "asset", "blocked.example.test", "recon").to_dict())
    store.put_observation(
        campaign.id,
        Observation(
            "endpoint:root",
            "endpoint",
            "https://example.test/api",
            "recon",
            parent_ids=("asset:root",),
        ).to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "endpoint:blocked",
            "endpoint",
            "https://blocked.example.test/api",
            "recon",
            parent_ids=("asset:blocked",),
        ).to_dict(),
    )

    result = campaign_attack_surface(campaign.id)

    assert result["summary"]["in_scope_endpoint_count"] == 1
    assert result["summary"]["out_of_scope_endpoint_count"] == 1
    assert {item["id"]: item["in_scope"] for item in result["endpoints"]} == {
        "endpoint:blocked": False,
        "endpoint:root": True,
    }
