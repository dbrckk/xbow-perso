from app.attack_surface import build_attack_surface, canonical_endpoint, canonical_host
from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def test_canonical_host_normalizes_case_and_trailing_dot():
    assert canonical_host("HTTPS://Example.TEST./path") == "example.test"
    assert canonical_host("Example.TEST.") == "example.test"


def test_canonical_endpoint_redacts_query_values_and_default_port():
    result = canonical_endpoint("HTTPS://Example.TEST:443/api/items?token=secret&id=42&id=43#frag")

    assert result == {
        "url": "https://example.test/api/items",
        "scheme": "https",
        "host": "example.test",
        "path": "/api/items",
        "parameter_names": ["id", "token"],
    }
    assert "secret" not in str(result)
    assert "42" not in str(result)


def test_attack_surface_snapshot_is_deterministic_and_read_only():
    graph = ObservationGraph()
    graph.add(Observation("asset:1", "asset", "Example.TEST", "recon"))
    graph.add(
        Observation(
            "endpoint:2",
            "endpoint",
            "https://example.test/b?z=secret",
            "recon",
            parent_ids=("asset:1",),
        )
    )
    graph.add(
        Observation(
            "endpoint:1",
            "endpoint",
            "https://EXAMPLE.test/a?x=1&x=2",
            "recon",
            parent_ids=("asset:1",),
        )
    )
    graph.add(
        Observation(
            "tech:1",
            "technology",
            "FastAPI",
            "fingerprint",
            parent_ids=("asset:1",),
        )
    )

    result = build_attack_surface(graph)

    assert result["read_only"] is True
    assert [item["url"] for item in result["endpoints"]] == [
        "https://example.test/a",
        "https://example.test/b",
    ]
    assert result["summary"]["hosts"] == {"example.test": 2}
    assert result["summary"]["schemes"] == {"https": 2}
    assert result["summary"]["parameter_names"] == ["x", "z"]
    assert "secret" not in str(result)


def test_attack_surface_route_is_exposed_and_reads_durable_graph(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="surface-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    store.put_observation(campaign.id, Observation("asset:1", "asset", "example.test", "recon").to_dict())
    store.put_observation(
        campaign.id,
        Observation(
            "endpoint:1",
            "endpoint",
            "https://example.test/api?token=redacted",
            "recon",
            parent_ids=("asset:1",),
        ).to_dict(),
    )

    from app.attack_surface import campaign_attack_surface

    result = campaign_attack_surface(campaign.id)

    assert "/api/campaigns/{campaign_id}/attack-surface" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["summary"]["endpoint_count"] == 1
    assert result["endpoints"][0]["parameter_names"] == ["token"]
    assert "redacted" not in str(result)
