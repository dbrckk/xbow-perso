from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.recon_swarm import build_recon_plan, campaign_recon_plan, recon_capabilities
from app.storage import Storage


def test_capabilities_are_bounded_read_only_and_get_head_only():
    capabilities = recon_capabilities()

    assert {item.agent for item in capabilities} == {
        "crawler-agent",
        "endpoint-agent",
        "tech-agent",
        "form-agent",
        "browser-agent",
    }
    assert all(item.read_only for item in capabilities)
    assert all(item.same_origin_only for item in capabilities)
    assert all(set(item.allowed_methods) <= {"GET", "HEAD"} for item in capabilities)
    assert all(item.max_targets_per_batch <= 10 for item in capabilities)
    assert all(item.max_requests_per_target <= 40 for item in capabilities)


def test_recon_plan_bootstraps_crawl_and_technology_context():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))

    tasks = build_recon_plan(
        "https://example.test/?token=secret",
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert [item.kind for item in tasks] == ["crawl", "detect_technology"]
    assert all(item.target == "https://example.test/" for item in tasks)
    assert all(item.read_only and item.same_origin_only for item in tasks)
    assert "secret" not in str([item.to_dict() for item in tasks])


def test_recon_plan_adds_form_and_browser_mapping_after_endpoints_exist():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=secret",
            "crawler",
            parent_ids=("asset:a",),
        )
    )

    tasks = build_recon_plan(
        "https://example.test",
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert [item.kind for item in tasks] == [
        "map_endpoints",
        "detect_technology",
        "map_forms",
        "browser_observe",
    ]
    assert all(set(item.allowed_methods) == {"GET", "HEAD"} for item in tasks)


def test_recon_plan_fails_closed_out_of_scope_and_invalid_limits():
    graph = ObservationGraph()

    assert build_recon_plan(
        "https://outside.test",
        graph,
        scope_checker=lambda host: host == "example.test",
    ) == []

    for invalid in (0, 26):
        try:
            build_recon_plan(
                "https://example.test",
                graph,
                scope_checker=lambda host: True,
                limit=invalid,
            )
        except ValueError as exc:
            assert "between 1 and 25" in str(exc)
        else:
            raise AssertionError("invalid recon plan limit should fail")


def test_recon_plan_route_is_exposed_and_scope_aware(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="recon-1",
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

    result = campaign_recon_plan(campaign.id)

    assert "/api/campaigns/{campaign_id}/recon-plan" in app.openapi()["paths"]
    assert "/api/recon-swarm/capabilities" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["bounded"] is True
    assert result["scope_aware"] is True
    assert result["execution"] == "advisory_only"


def test_recon_plan_refuses_unobserved_host_when_asset_inventory_exists():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))

    tasks = build_recon_plan(
        "https://other.test",
        graph,
        scope_checker=lambda host: host in {"example.test", "other.test"},
    )

    assert tasks == []
