from app.finding_correlation import (
    campaign_finding_clusters,
    campaign_finding_correlations,
    cluster_findings,
    correlate_findings,
    score_finding_similarity,
)
from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.storage import Storage


def _finding(finding_id: str, endpoint: str, *, severity: str = "medium"):
    return Finding(
        id=finding_id,
        title=f"fixture {finding_id}",
        severity=severity,
        asset="https://EXAMPLE.test:443",
        endpoint=endpoint,
        summary="bounded fixture",
        cwe="CWE-79",
        discovered_by="scanner",
    )


def test_correlates_canonical_duplicate_findings_without_query_values():
    findings = [
        _finding("f1", "https://example.test:443/account?id=1", severity="medium"),
        _finding("f2", "HTTPS://EXAMPLE.TEST/account?id=secret", severity="high"),
    ]

    groups = correlate_findings(findings)

    assert len(groups) == 1
    group = groups[0]
    assert group.finding_ids == ("f1", "f2")
    assert group.endpoint == "https://example.test/account"
    assert group.highest_severity == "high"
    assert group.duplicate_candidate is True
    assert "secret" not in str(group.to_dict())


def test_different_cwe_or_endpoint_stays_separate():
    first = _finding("f1", "https://example.test/a")
    second = _finding("f2", "https://example.test/b")
    second.cwe = "CWE-200"

    groups = correlate_findings([first, second])

    assert len(groups) == 2
    assert all(item.duplicate_candidate is False for item in groups)


def test_correlation_route_is_exposed_and_does_not_auto_merge(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="correlation-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            _finding("f1", "https://example.test/a?token=one"),
            _finding("f2", "https://example.test/a?token=two", severity="high"),
        ],
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    result = campaign_finding_correlations(campaign.id)

    assert "/api/campaigns/{campaign_id}/finding-correlations" in app.openapi()["paths"]
    assert result["read_only"] is True
    assert result["auto_merge"] is False
    assert result["summary"] == {
        "groups": 1,
        "duplicate_groups": 1,
        "findings_in_duplicate_groups": 2,
    }
    assert "one" not in str(result)
    assert "two" not in str(result)



def test_similarity_scores_same_asset_endpoint_and_cwe_highly():
    left = _finding("f1", "https://example.test/a?id=one")
    right = _finding("f2", "https://EXAMPLE.TEST:443/a?id=two")
    left.title = "Reflected script injection in account page"
    right.title = "Account page reflected script injection"

    similarity = score_finding_similarity(left, right)

    assert similarity.same_asset is True
    assert similarity.same_endpoint is True
    assert similarity.same_cwe is True
    assert similarity.score >= 0.85
    assert set(similarity.reasons) >= {"asset", "endpoint", "cwe"}
    assert "one" not in str(similarity.to_dict())
    assert "two" not in str(similarity.to_dict())


def test_similarity_caps_cross_asset_generic_matches():
    left = _finding("f1", "https://example.test/a")
    right = _finding("f2", "https://other.test/a")
    right.asset = "https://other.test"
    left.title = right.title = "Generic reflected script injection"

    similarity = score_finding_similarity(left, right)

    assert similarity.same_asset is False
    assert similarity.score <= 0.40


def test_cluster_findings_groups_high_confidence_pairs_without_merging():
    first = _finding("f1", "https://example.test/a?id=1")
    second = _finding("f2", "https://example.test/a?id=2")
    third = _finding("f3", "https://example.test/b")
    third.cwe = "CWE-200"

    clusters, similarities = cluster_findings([first, second, third], threshold=0.75)

    assert len(clusters) == 1
    assert clusters[0].finding_ids == ("f1", "f2")
    assert clusters[0].confidence >= 0.75
    assert clusters[0].auto_merge is False
    assert any(item.left_id == "f1" and item.right_id == "f2" for item in similarities)


def test_cluster_threshold_fails_closed():
    findings = [_finding("f1", "https://example.test/a")]

    for invalid in (0.49, 1.01):
        try:
            cluster_findings(findings, threshold=invalid)
        except ValueError as exc:
            assert "between 0.50 and 1.0" in str(exc)
        else:
            raise AssertionError("invalid cluster threshold should fail")


def test_cluster_route_is_exposed(tmp_path, monkeypatch):
    db = str(tmp_path / "clusters.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="clusters-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            _finding("f1", "https://example.test/a?id=one"),
            _finding("f2", "https://example.test/a?id=two"),
        ],
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    result = campaign_finding_clusters(campaign.id)

    assert "/api/campaigns/{campaign_id}/finding-clusters" in app.openapi()["paths"]
    assert result["read_only"] is True
    assert result["auto_merge"] is False
    assert result["explainable"] is True
    assert result["summary"]["clusters"] == 1
    assert "one" not in str(result)
    assert "two" not in str(result)
