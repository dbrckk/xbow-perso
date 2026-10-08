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


def test_recon_plan_accepts_matching_bare_asset_host():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "Example.TEST.", "inventory"))

    tasks = build_recon_plan(
        "https://example.test",
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert tasks
    assert all(item.target == "https://example.test/" for item in tasks)


def test_recon_plan_reorders_existing_tasks_after_null_scans(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="recon-null-feedback",
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
    store.put_observation(
        campaign.id,
        Observation("asset:a", "asset", "example.test", "inventory").to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "endpoint:a",
            "endpoint",
            "https://example.test/account?id=secret",
            "crawler",
            parent_ids=("asset:a",),
        ).to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "scan:completed",
            "evidence",
            "completed",
            "nuclei",
            metadata={"phase": "scan", "status": "completed"},
        ).to_dict(),
    )

    result = campaign_recon_plan(campaign.id)
    feedback = result["no_finding_feedback"]

    assert feedback["state"] == "recovery_advisory"
    assert feedback["completed_scan_count"] == 1
    assert feedback["recommended_task_kinds"][:2] == [
        "map_forms", "detect_technology"
    ]
    adjustments = {
        item["kind"]: item
        for item in result["diff_priority"]["adjustments"]
    }
    assert adjustments["map_forms"]["no_finding_boost"] == 24
    assert adjustments["detect_technology"]["no_finding_boost"] == 16
    assert adjustments["map_endpoints"]["no_finding_boost"] == 8
    assert adjustments["map_forms"]["effective_priority"] > 70
    assert result["diff_priority"]["new_tasks_created"] is False
    assert all(item["same_origin_only"] is True for item in result["tasks"])
    assert all(set(item["allowed_methods"]) <= {"GET", "HEAD"} for item in result["tasks"])
    assert all(item["max_requests"] <= 40 for item in result["tasks"])
    assert "secret" not in str(result["tasks"])
    assert "secret" not in str(result["no_finding_feedback"])
    # Surface diff, temporal, confidence and target memory must also redact
    # parameter values before the full API response is returned.
    assert "secret" not in str(result)


def test_multi_host_recon_ignores_inventory_from_other_authorized_host():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "a.example.test", "inventory"))
    graph.add(Observation("asset:b", "asset", "b.example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:b",
            "endpoint",
            "https://b.example.test/api",
            "crawler",
            parent_ids=("asset:b",),
        )
    )
    for kind in ("form", "technology", "waf"):
        value = (
            "https://b.example.test/login" if kind == "form" else "nginx/1.24.0"
        )
        graph.add(
            Observation(
                f"{kind}:b",
                kind,
                value,
                "scanner",
                parent_ids=("asset:b",),
            )
        )

    tasks = build_recon_plan(
        "https://a.example.test/",
        graph,
        scope_checker=lambda host: host in {"a.example.test", "b.example.test"},
    )

    assert [task.kind for task in tasks] == ["crawl", "detect_technology"]
    assert all(task.target == "https://a.example.test/" for task in tasks)
    assert all(task.max_requests <= 40 for task in tasks)


def test_recon_does_not_reuse_http_inventory_on_https_origin():
    graph = ObservationGraph()
    graph.add(Observation("asset:http", "asset", "http://example.test", "recon"))
    graph.add(Observation("asset:https", "asset", "https://example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:http",
            "endpoint",
            "http://example.test/api",
            "crawler",
            parent_ids=("asset:http",),
        )
    )

    tasks = build_recon_plan(
        "https://example.test",
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert [task.kind for task in tasks] == ["crawl", "detect_technology"]


def test_recon_does_not_reuse_another_port_form_or_technology():
    graph = ObservationGraph()
    graph.add(Observation("asset:443", "asset", "https://example.test", "recon"))
    graph.add(
        Observation(
            "asset:8443",
            "asset",
            "https://example.test:8443",
            "recon",
        )
    )
    graph.add(
        Observation(
            "endpoint:443",
            "endpoint",
            "https://example.test/api",
            "crawler",
            parent_ids=("asset:443",),
        )
    )
    graph.add(
        Observation(
            "form:8443",
            "form",
            "https://example.test:8443/login",
            "form-agent",
            parent_ids=("asset:8443",),
        )
    )
    graph.add(
        Observation(
            "technology:8443",
            "technology",
            "nginx/1.24.0",
            "httpx",
            parent_ids=("asset:8443",),
        )
    )

    tasks = build_recon_plan(
        "https://example.test",
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    kinds = [task.kind for task in tasks]
    assert kinds == [
        "map_endpoints",
        "detect_technology",
        "map_forms",
        "browser_observe",
    ]


def test_unlinked_observation_from_multi_asset_graph_is_not_coverage():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "a.example.test", "inventory"))
    graph.add(Observation("asset:b", "asset", "b.example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:legacy",
            "endpoint",
            "https://a.example.test/api",
            "legacy-import",
        )
    )

    tasks = build_recon_plan(
        "https://a.example.test",
        graph,
        scope_checker=lambda host: True,
    )

    assert [task.kind for task in tasks] == ["crawl", "detect_technology"]


def test_single_host_legacy_unlinked_endpoint_still_counts_when_origin_matches():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:legacy",
            "endpoint",
            "https://example.test/api",
            "legacy-import",
        )
    )

    tasks = build_recon_plan(
        "https://example.test",
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert "map_endpoints" in [task.kind for task in tasks]
    assert "crawl" not in [task.kind for task in tasks]


def test_recon_rejects_non_http_or_credential_bearing_target():
    graph = ObservationGraph()
    for value in (
        "ftp://example.test/data",
        "https://user:password@example.test/",
        "https://example.test:invalid/path",
        "https://[invalid-ipv6",
    ):
        assert build_recon_plan(
            value,
            graph,
            scope_checker=lambda host: host == "example.test",
        ) == []


def test_recon_ipv6_target_keeps_bracketed_origin_and_read_only_limits():
    graph = ObservationGraph()
    graph.add(Observation("asset:ipv6", "asset", "https://[::1]", "inventory"))
    tasks = build_recon_plan(
        "https://[::1]:443/path?secret=sensitive",
        graph,
        scope_checker=lambda host: host == "::1",
    )

    assert [task.kind for task in tasks] == ["crawl", "detect_technology"]
    assert all(task.target == "https://[::1]/path" for task in tasks)
    assert "sensitive" not in str([task.to_dict() for task in tasks])
    assert all(
        task.read_only and task.same_origin_only
        and set(task.allowed_methods) <= {"GET", "HEAD"}
        for task in tasks
    )
