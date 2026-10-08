from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.red_team_coverage import build_red_team_coverage, campaign_red_team_coverage
from app.storage import Storage


def test_red_team_coverage_reports_gaps_without_executing_actions():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=secret",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("endpoint:e",),
        )
    )

    result = build_red_team_coverage(graph)

    assert result["read_only"] is True
    assert result["safe_validation_only"] is True
    assert result["summary"]["observed_endpoints"] == 1
    assert result["summary"]["reviewed_endpoints"] == 0
    assert result["summary"]["observed_findings"] == 1
    assert result["summary"]["independently_validated_findings"] == 0
    assert "authorization_review_pending" in result["gaps"]
    assert "input_review_pending" in result["gaps"]
    assert "independent_validation_pending" in result["gaps"]
    assert "secret" not in str(result)


def test_endpoint_review_credit_requires_recorded_review_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=1",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    before = build_red_team_coverage(graph)

    graph.add(
        Observation(
            "evidence:review",
            "evidence",
            "review-recorded",
            "review-agent",
            parent_ids=("endpoint:e",),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )
    after = build_red_team_coverage(graph)

    assert before["summary"]["reviewed_endpoints"] == 0
    assert after["summary"]["reviewed_endpoints"] == 1
    assert after["score"] > before["score"]


def test_red_team_coverage_improves_after_independent_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("asset:a",)))
    before = build_red_team_coverage(graph)

    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:x1",
            "evidence",
            "artifact-reference",
            "independent-validator",
            parent_ids=("validation:v1",),
        )
    )
    after = build_red_team_coverage(graph)

    assert after["score"] > before["score"]
    assert after["summary"]["independently_validated_findings"] == 1
    assert after["summary"]["complete_evidence_chains"] == 1
    assert "independent_validation_pending" not in after["gaps"]
    assert "evidence_chain_incomplete" not in after["gaps"]


def test_red_team_coverage_route_is_exposed_and_reads_durable_graph(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="coverage-1",
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
    store.put_observation(campaign.id, Observation("asset:a", "asset", "example.test", "recon").to_dict())

    result = campaign_red_team_coverage(campaign.id)

    assert "/api/campaigns/{campaign_id}/red-team-coverage" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["safe_validation_only"] is True


def test_red_team_coverage_ignores_failed_or_queued_review_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/settings",
            "recon",
            parent_ids=("asset:a",),
        )
    )

    for status in ("failed", "queued"):
        graph.add(
            Observation(
                f"review:{status}",
                "evidence",
                "review-attempt",
                "review-agent",
                parent_ids=("endpoint:e",),
                metadata={
                    "review_type": "authorization_surface_review",
                    "status": status,
                },
            )
        )

    before = build_red_team_coverage(graph)
    assert before["summary"]["reviewed_endpoints"] == 0

    graph.add(
        Observation(
            "review:complete",
            "evidence",
            "review-recorded",
            "review-agent",
            parent_ids=("endpoint:e",),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )
    after = build_red_team_coverage(graph)
    assert after["summary"]["reviewed_endpoints"] == 1
    assert after["score"] >= before["score"]
    assert after["read_only"] is True


def test_empty_graph_has_zero_observed_coverage_not_full_score():
    result = build_red_team_coverage(ObservationGraph())

    assert result["score"] == 0.0
    assert result["observation_state"] == "no_observed_surface"
    assert result["summary"]["observed_domain_count"] == 0
    assert result["summary"]["unobserved_domain_count"] == 6
    assert len(result["unobserved_domains"]) == 6
    assert all(item["score"] == 0.0 for item in result["domains"])
    assert result["read_only"] is True
    assert result["safe_validation_only"] is True


def test_asset_only_graph_does_not_claim_full_review_coverage():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    result = build_red_team_coverage(graph)

    assert result["score"] == 0.0
    assert result["observation_state"] == "no_observed_surface"
    assert result["unobserved_domains"]
    assert result["score_interpretation"].endswith("not_security_assurance")


def test_completed_review_raises_observed_surface_score_without_security_claim():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/",
            "recon",
            parent_ids=("asset:a",),
        )
    )

    before = build_red_team_coverage(graph)
    graph.add(
        Observation(
            "review:endpoint",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:e",),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )
    after = build_red_team_coverage(graph)

    assert before["score"] == 0.0
    assert after["score"] == 1.0
    assert after["observation_state"] == "observed_surface_only"
    assert after["summary"]["observed_domain_count"] == 1
    assert after["summary"]["unobserved_domain_count"] == 5
    assert "form_surface" in after["unobserved_domains"]
    assert "not_security_assurance" in after["score_interpretation"]


def test_unvalidated_finding_reduces_score_across_observed_dimensions():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("asset:a",),
        )
    )
    result = build_red_team_coverage(graph)

    assert result["observation_state"] == "observed_surface_only"
    assert result["score"] == 0.0
    assert result["summary"]["observed_domain_count"] == 2
    assert "finding_validation" not in result["unobserved_domains"]
    assert "evidence_quality" not in result["unobserved_domains"]


def test_mixed_parent_endpoint_review_cannot_close_in_scope_gap():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(Observation("asset:b", "asset", "other.test", "recon"))
    graph.add(
        Observation(
            "endpoint:a",
            "endpoint",
            "https://example.test/settings",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "review:mixed",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:a", "asset:b"),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )

    result = build_red_team_coverage(
        graph, scope_checker=lambda host: host == "example.test"
    )

    assert result["summary"]["observed_endpoints"] == 1
    assert result["summary"]["reviewed_endpoints"] == 0
    assert result["domains"][0]["gaps"] == 1
    assert result["read_only"] is True


def test_review_spanning_in_scope_and_out_of_scope_endpoints_is_not_credited():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(Observation("asset:b", "asset", "other.test", "recon"))
    graph.add(
        Observation(
            "endpoint:a",
            "endpoint",
            "https://example.test/settings",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "endpoint:b",
            "endpoint",
            "https://other.test/settings",
            "recon",
            parent_ids=("asset:b",),
        )
    )
    graph.add(
        Observation(
            "review:both",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:a", "endpoint:b"),
            metadata={
                "review_type": "input_surface_review",
                "status": "completed",
            },
        )
    )

    result = build_red_team_coverage(
        graph, scope_checker=lambda host: host == "example.test"
    )

    assert result["summary"]["observed_endpoints"] == 1
    assert result["summary"]["reviewed_endpoints"] == 0


def test_form_review_with_mixed_endpoint_parent_does_not_close_form_gap():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:a",
            "endpoint",
            "https://example.test/login",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "form:a",
            "form",
            "https://example.test/login",
            "recon",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "review:mixed-form",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("form:a", "endpoint:a"),
            metadata={
                "review_type": "form_surface_review",
                "status": "completed",
            },
        )
    )

    result = build_red_team_coverage(graph)

    assert result["summary"]["observed_forms"] == 1
    assert result["summary"]["reviewed_forms"] == 0


def test_completed_review_of_multiple_eligible_endpoints_is_creditable():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    for name in ("one", "two"):
        graph.add(
            Observation(
                f"endpoint:{name}",
                "endpoint",
                f"https://example.test/{name}",
                "recon",
                parent_ids=("asset:a",),
            )
        )
    graph.add(
        Observation(
            "review:both",
            "evidence",
            "reviewed",
            "analyst",
            parent_ids=("endpoint:one", "endpoint:two"),
            metadata={
                "review_type": "authorization_surface_review",
                "status": "completed",
            },
        )
    )

    result = build_red_team_coverage(
        graph, scope_checker=lambda host: host == "example.test"
    )

    assert result["summary"]["reviewed_endpoints"] == 2
    assert result["summary"]["observed_endpoints"] == 2
    assert result["domains"][0]["gaps"] == 0
