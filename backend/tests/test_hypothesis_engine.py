from app.hypothesis_engine import build_hypotheses, campaign_hypotheses
from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def test_hypotheses_are_bounded_and_deterministic():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://example.test/account?id=1",
            "recon",
            parent_ids=("a1",),
        )
    )
    graph.add(Observation("t1", "technology", "framework-x", "recon", parent_ids=("a1",)))

    first = build_hypotheses(graph, limit=2)
    second = build_hypotheses(graph, limit=2)

    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert len(first) == 2
    assert first[0].kind == "authorization_surface_review"
    assert all(item.next_action in {"scan", "validate", "stop"} for item in first)
    assert all(item.read_only is True for item in first)


def test_hypothesis_redacts_query_values_and_keeps_parameter_names():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "e1",
            "endpoint",
            "https://EXAMPLE.test:443/account?token=super-secret&id=42#private",
            "recon",
            parent_ids=("a1",),
        )
    )

    hypotheses = build_hypotheses(graph)
    payload = [item.to_dict() for item in hypotheses]

    assert {item["target"] for item in payload} == {"https://example.test/account"}
    assert all(item["parameter_names"] == ["id", "token"] for item in payload)
    assert "super-secret" not in str(payload)
    assert "42" not in str(payload)
    assert "private" not in str(payload)


def test_scope_checker_filters_out_of_scope_lineage():
    graph = ObservationGraph()
    graph.add(Observation("inside", "asset", "example.test", "recon"))
    graph.add(Observation("outside", "asset", "outside.test", "recon"))
    graph.add(
        Observation(
            "e-in",
            "endpoint",
            "https://example.test/account?id=1",
            "recon",
            parent_ids=("inside",),
        )
    )
    graph.add(
        Observation(
            "e-out",
            "endpoint",
            "https://outside.test/account?id=2",
            "recon",
            parent_ids=("outside",),
        )
    )

    hypotheses = build_hypotheses(
        graph,
        scope_checker=lambda host: host == "example.test",
    )
    payload = [item.to_dict() for item in hypotheses]

    assert payload
    assert all(item["target"].startswith("https://example.test/") for item in payload)
    assert "outside.test" not in str(payload)


def test_unvalidated_finding_gets_high_priority_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))

    hypotheses = build_hypotheses(graph)

    assert hypotheses[0].kind == "validation_gap"
    assert hypotheses[0].confidence == 0.90
    assert hypotheses[0].next_action == "validate"


def test_observed_independent_validation_closes_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )

    assert build_hypotheses(graph) == []


def test_self_validation_does_not_close_validation_gap():
    graph = ObservationGraph()
    graph.add(Observation("a1", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)))
    graph.add(
        Observation(
            "v1",
            "validation",
            "observed",
            "scanner",
            parent_ids=("finding:f1",),
        )
    )

    hypotheses = build_hypotheses(graph)
    assert hypotheses[0].kind == "validation_gap"


def test_hypothesis_route_is_exposed_and_reads_durable_graph(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="hypothesis-1",
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
    store.put_observation(campaign.id, Observation("a1", "asset", "example.test", "recon").to_dict())
    store.put_observation(
        campaign.id,
        Observation(
            "e1",
            "endpoint",
            "https://example.test/profile?session=do-not-leak",
            "recon",
            parent_ids=("a1",),
        ).to_dict(),
    )

    result = campaign_hypotheses(campaign.id)

    assert "/api/campaigns/{campaign_id}/hypotheses" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["safe_validation_only"] is True
    assert result["scope_aware"] is True
    assert result["summary"]["total"] == 2
    assert result["summary"]["by_kind"] == {
        "authorization_surface_review": 1,
        "input_surface_review": 1,
    }
    assert "do-not-leak" not in str(result)


def test_limit_fails_closed_outside_bounds():
    graph = ObservationGraph()

    for invalid in (0, 101):
        try:
            build_hypotheses(graph, limit=invalid)
        except ValueError as exc:
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("invalid limit should fail")


def test_mixed_in_and_out_of_scope_ancestors_never_authorize_review():
    graph = ObservationGraph()
    graph.add(Observation("asset:in", "asset", "example.test", "recon"))
    graph.add(Observation("asset:out", "asset", "outside.test", "recon"))
    graph.add(
        Observation(
            "endpoint:mixed",
            "endpoint",
            "https://example.test/account?id=1",
            "recon",
            parent_ids=("asset:in", "asset:out"),
        )
    )
    graph.add(
        Observation(
            "form:mixed",
            "form",
            "https://example.test/login",
            "browser",
            parent_ids=("asset:in", "asset:out"),
        )
    )
    graph.add(
        Observation(
            "technology:mixed",
            "technology",
            "nginx/1.24.0",
            "recon",
            parent_ids=("asset:in", "asset:out"),
        )
    )

    assert build_hypotheses(
        graph,
        scope_checker=lambda host: host == "example.test",
    ) == []


def test_scoped_orphan_technology_cannot_be_attributed_to_allowed_target():
    graph = ObservationGraph()
    graph.add(
        Observation("technology:orphan", "technology", "nginx", "recon")
    )

    assert build_hypotheses(
        graph, scope_checker=lambda host: host == "example.test"
    ) == []


def test_invalid_and_credentialed_endpoints_are_not_review_hypotheses():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    for index, value in enumerate((
        "ftp://example.test/account?id=1",
        "https://user:secret@example.test/account?id=2",
        "https://example.test:0/account?id=3",
        "https://[invalid-ipv6/account?id=4",
        "https://example.test/acc\\nount?id=5".replace("\\n", "\n"),
    )):
        graph.add(
            Observation(
                f"endpoint:{index}", "endpoint", value, "recon",
                parent_ids=("asset:a",),
            )
        )

    assert build_hypotheses(graph) == []


def test_invalid_form_url_cannot_generate_form_review():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "form:bad", "form", "https://user:password@example.test/login",
            "recon", parent_ids=("asset:a",),
        )
    )

    assert build_hypotheses(graph) == []


def test_ipv6_endpoint_hypothesis_is_redacted_and_bracketed():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "endpoint:ipv6",
            "endpoint",
            "https://[2001:db8::1]:8443/account?id=42&token=secret",
            "recon",
        )
    )

    result = build_hypotheses(graph)

    assert len(result) == 2
    assert all(
        item.target == "https://[2001:db8::1]:8443/account"
        for item in result
    )
    assert "secret" not in str([item.to_dict() for item in result])


def test_scoped_hypotheses_keep_valid_authorized_asset_lineage():
    graph = ObservationGraph()
    graph.add(Observation("asset:allowed", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:allowed",
            "endpoint",
            "https://example.test/profile?token=private",
            "recon",
            parent_ids=("asset:allowed",),
        )
    )

    result = build_hypotheses(
        graph, scope_checker=lambda host: host == "example.test"
    )
    assert {item.kind for item in result} == {
        "input_surface_review", "authorization_surface_review"
    }
    assert "private" not in str([item.to_dict() for item in result])


def test_duplicate_url_merges_distinct_parameter_names_and_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:target", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:alpha",
            "endpoint",
            "https://example.test/search?q=secret-one",
            "crawler",
            parent_ids=("asset:target",),
        )
    )
    graph.add(
        Observation(
            "endpoint:beta",
            "endpoint",
            "https://example.test/search?page=secret-two",
            "browser",
            parent_ids=("asset:target",),
        )
    )

    results = build_hypotheses(
        graph, scope_checker=lambda host: host == "example.test"
    )

    assert len(results) == 1
    assert results[0].kind == "input_surface_review"
    assert results[0].target == "https://example.test/search"
    assert results[0].parameter_names == ("page", "q")
    assert results[0].evidence_ids == (
        "endpoint:alpha", "endpoint:beta"
    )
    assert results[0].confidence == 0.55
    assert "secret-one" not in str([item.to_dict() for item in results])
    assert "secret-two" not in str([item.to_dict() for item in results])


def test_duplicate_url_hypotheses_are_order_independent():
    def build_graph(reverse: bool) -> ObservationGraph:
        graph = ObservationGraph()
        graph.add(Observation("asset:a", "asset", "example.test", "recon"))
        observations = [
            Observation(
                "endpoint:one", "endpoint",
                "https://example.test/account?role=private",
                "crawler", parent_ids=("asset:a",),
            ),
            Observation(
                "endpoint:two", "endpoint",
                "https://example.test/account?page=private",
                "browser", parent_ids=("asset:a",),
            ),
        ]
        for item in reversed(observations) if reverse else observations:
            graph.add(item)
        return graph

    forward = build_hypotheses(build_graph(False))
    backward = build_hypotheses(build_graph(True))

    assert [item.to_dict() for item in forward] == [
        item.to_dict() for item in backward
    ]
    assert len(forward) == 2
    assert all(
        item.evidence_ids == ("endpoint:one", "endpoint:two")
        for item in forward
    )
    assert all(
        item.parameter_names == ("page", "role")
        for item in forward
    )


def test_query_evidence_merge_stays_bounded_for_many_observations():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    for index in range(50):
        graph.add(
            Observation(
                f"endpoint:{index:03d}",
                "endpoint",
                f"https://example.test/search?key{index:03d}=private",
                "crawler",
                parent_ids=("asset:a",),
            )
        )

    matches = build_hypotheses(graph)
    assert len(matches) == 1
    assert len(matches[0].evidence_ids) == 32
    assert len(matches[0].parameter_names) == 50
    assert matches[0].evidence_ids[0] == "endpoint:000"
    assert matches[0].parameter_names[0] == "key000"
    assert "private" not in str([item.to_dict() for item in matches])


def test_distinct_targets_and_review_kinds_do_not_mix_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:account",
            "endpoint",
            "https://example.test/account?id=private",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "endpoint:search",
            "endpoint",
            "https://example.test/search?q=private",
            "crawler",
            parent_ids=("asset:a",),
        )
    )
    results = build_hypotheses(graph)
    grouped = {(item.kind, item.target): item for item in results}

    assert len(results) == 3
    assert grouped[
        ("authorization_surface_review", "https://example.test/account")
    ].evidence_ids == ("endpoint:account",)
    assert grouped[
        ("input_surface_review", "https://example.test/search")
    ].evidence_ids == ("endpoint:search",)
