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
        "valid": True,
        "error": None,
    }
    assert "secret" not in str(result)
    assert "42" not in str(result)


def test_canonical_endpoint_flags_invalid_port_without_leaking_query_values():
    result = canonical_endpoint("https://example.test:not-a-port/api?token=secret")

    assert result["valid"] is False
    assert result["error"] == "invalid_port"
    assert result["url"] == ""
    assert result["parameter_names"] == ["token"]
    assert "secret" not in str(result)


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
    assert result["summary"]["endpoint_sources"] == {"recon": 2}
    assert result["summary"]["unique_endpoint_count"] == 2
    assert result["summary"]["duplicate_endpoint_count"] == 0
    assert result["summary"]["invalid_endpoint_count"] == 0
    assert result["summary"]["parameter_names"] == ["x", "z"]
    assert "secret" not in str(result)


def test_attack_surface_models_forms_and_waf_without_secrets():
    graph = ObservationGraph()
    graph.add(Observation("asset:1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "form:1",
            "form",
            "https://example.test/login?csrf=secret-value",
            "browser",
            parent_ids=("asset:1",),
            metadata={"method": "POST", "input_names": ["username", "password", "username"]},
        )
    )
    graph.add(
        Observation(
            "waf:1",
            "waf",
            "cloud-edge-waf",
            "fingerprint",
            parent_ids=("asset:1",),
            metadata={"confidence": 0.8},
        )
    )

    result = build_attack_surface(graph, scope_checker=lambda host: host == "example.test")

    assert result["forms"] == [
        {
            "id": "form:1",
            "action": "https://example.test/login",
            "host": "example.test",
            "method": "POST",
            "input_names": ["password", "username"],
            "valid": True,
            "in_scope": True,
            "source": "browser",
            "parent_ids": ["asset:1"],
        }
    ]
    assert result["wafs"][0]["name"] == "cloud-edge-waf"
    assert result["wafs"][0]["confidence"] == 0.8
    assert result["summary"]["form_count"] == 1
    assert result["summary"]["waf_count"] == 1
    assert result["summary"]["form_input_names"] == ["password", "username"]
    assert "secret-value" not in str(result)


def test_attack_surface_counts_canonical_duplicates_and_invalid_entries():
    graph = ObservationGraph()
    graph.add(Observation("asset:1", "asset", "example.test", "recon"))
    graph.add(Observation("endpoint:1", "endpoint", "https://example.test:443/api?a=1", "recon", parent_ids=("asset:1",)))
    graph.add(Observation("endpoint:2", "endpoint", "HTTPS://EXAMPLE.TEST/api?a=2", "browser", parent_ids=("asset:1",)))
    graph.add(Observation("endpoint:3", "endpoint", "https://example.test:bad/api?secret=value", "recon", parent_ids=("asset:1",)))

    result = build_attack_surface(graph)

    assert result["summary"]["endpoint_count"] == 3
    assert result["summary"]["valid_endpoint_count"] == 2
    assert result["summary"]["invalid_endpoint_count"] == 1
    assert result["summary"]["unique_endpoint_count"] == 1
    assert result["summary"]["duplicate_endpoint_count"] == 1
    assert result["summary"]["endpoint_sources"] == {"browser": 1, "recon": 1}
    assert "value" not in str(result)


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
    assert result["summary"]["valid_endpoint_count"] == 1
    assert result["endpoints"][0]["parameter_names"] == ["token"]
    assert "redacted" not in str(result)


def test_attack_surface_enrichment_score_rewards_cross_source_context():
    graph = ObservationGraph()
    graph.add(Observation("asset:1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:1",
            "endpoint",
            "https://example.test/a",
            "recon:crawl",
            parent_ids=("asset:1",),
        )
    )
    graph.add(
        Observation(
            "form:1",
            "form",
            "https://example.test/search",
            "browser",
            parent_ids=("asset:1",),
            metadata={"method": "GET", "input_names": ["q"]},
        )
    )
    graph.add(
        Observation(
            "tech:1",
            "technology",
            "next",
            "browser",
            parent_ids=("asset:1",),
        )
    )

    result = build_attack_surface(graph)

    assert result["summary"]["surface_sources"] == ["browser", "recon:crawl"]
    assert result["summary"]["source_diversity"] == 2
    assert result["summary"]["enrichment_score"] > 0.7


def test_canonical_endpoint_rejects_unsupported_web_schemes_and_credentials():
    invalid = (
        ("ftp://example.test/archive?token=hidden", "unsupported_scheme"),
        ("https://user:password@example.test/login?token=hidden", "embedded_credentials"),
        ("https://example.test:0/path?token=hidden", "invalid_port"),
    )
    for value, reason in invalid:
        endpoint = canonical_endpoint(value)
        assert endpoint["valid"] is False
        assert endpoint["error"] == reason
        assert endpoint["url"] == ""
        assert "hidden" not in str(endpoint)
        assert "password" not in str(endpoint)


def test_malformed_ipv6_does_not_crash_attack_surface_summary():
    graph = ObservationGraph()
    graph.add(
        Observation("asset:bad", "asset", "https://[invalid-ipv6", "recon")
    )
    graph.add(
        Observation(
            "endpoint:bad",
            "endpoint",
            "https://[invalid-ipv6/secret",
            "recon",
            parent_ids=("asset:bad",),
        )
    )
    result = build_attack_surface(
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert canonical_host("https://[invalid-ipv6") == ""
    assert result["summary"]["invalid_endpoint_count"] == 1
    assert result["summary"]["in_scope_asset_count"] == 0
    assert result["endpoints"][0]["error"] == "invalid_url"
    assert result["endpoints"][0]["url"] == ""


def test_canonical_ipv6_endpoint_keeps_valid_brackets_and_port():
    endpoint = canonical_endpoint(
        "https://[::1]:8443/api?token=hidden"
    )
    assert endpoint["valid"] is True
    assert endpoint["url"] == "https://[::1]:8443/api"
    assert endpoint["host"] == "::1"
    assert "hidden" not in str(endpoint)


def test_invalid_protocol_and_credentialed_form_do_not_raise_surface_coverage():
    graph = ObservationGraph()
    graph.add(
        Observation("asset:a", "asset", "example.test", "recon")
    )
    graph.add(
        Observation(
            "endpoint:ftp",
            "endpoint",
            "ftp://example.test/archive",
            "import",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "form:credentialed",
            "form",
            "https://user:secret@example.test/login",
            "browser",
            parent_ids=("asset:a",),
        )
    )
    result = build_attack_surface(
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert result["summary"]["valid_endpoint_count"] == 0
    assert result["summary"]["valid_form_count"] == 0
    assert result["summary"]["in_scope_endpoint_count"] == 0
    assert result["summary"]["in_scope_form_count"] == 0
    assert all(item["in_scope"] is None for item in result["endpoints"])
    assert all(item["in_scope"] is None for item in result["forms"])
    assert "secret" not in str(result)


def test_canonical_host_rejects_credential_bearing_or_unsupported_asset():
    assert canonical_host("https://user:secret@example.test") == ""
    assert canonical_host("ftp://example.test") == ""
    assert canonical_host("https://example.test") == "example.test"


def test_url_control_characters_cannot_change_host_identity():
    # urllib.parse removes tabs/newlines unless rejected before parsing.
    values = ("https://exa\\nmple.test/path", "https://example.test\\t/path")
    for escaped in values:
        raw = escaped.encode("utf-8").decode("unicode_escape")
        assert canonical_host(raw) == ""
        item = canonical_endpoint(raw)
        assert item["valid"] is False
        assert item["error"] == "invalid_url"
        assert item["url"] == ""


def test_invalid_endpoint_sources_do_not_inflate_discovery_confidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:valid",
            "endpoint",
            "https://example.test/api",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    baseline = build_attack_surface(graph)
    graph.add(
        Observation(
            "endpoint:invalid",
            "endpoint",
            "ftp://example.test/archive",
            "untrusted-import",
            parent_ids=("asset:a",),
        )
    )
    result = build_attack_surface(graph)

    assert baseline["summary"]["source_diversity"] == 1
    assert result["summary"]["source_diversity"] == 1
    assert result["summary"]["surface_sources"] == ["crawler"]
    assert result["summary"]["enrichment_score"] == baseline["summary"]["enrichment_score"]
    assert result["summary"]["invalid_endpoint_count"] == 1


def test_invalid_form_sources_cannot_count_as_independent_surface_discovery():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "form:invalid",
            "form",
            "https://user:secret@example.test/login",
            "untrusted-form-source",
            parent_ids=("asset:a",),
        )
    )

    result = build_attack_surface(graph)

    assert result["summary"]["valid_form_count"] == 0
    assert result["summary"]["source_diversity"] == 0
    assert result["summary"]["surface_sources"] == []
    assert result["summary"]["enrichment_score"] == 0.0
    assert "secret" not in str(result)


def test_valid_multi_source_surface_still_rewards_independent_discovery():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(
        Observation(
            "endpoint:valid",
            "endpoint",
            "https://example.test/api",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "form:valid",
            "form",
            "https://example.test/form",
            "browser",
            parent_ids=("asset:a",),
        )
    )

    result = build_attack_surface(graph)

    assert result["summary"]["source_diversity"] == 2
    assert result["summary"]["surface_sources"] == ["browser", "crawler"]
    assert result["summary"]["enrichment_score"] > 0.5
