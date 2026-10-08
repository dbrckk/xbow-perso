from datetime import datetime, timezone
from types import SimpleNamespace

from app.observation_graph import Observation, ObservationGraph
from app.technology_fingerprint_intelligence import (
    build_finding_fingerprint_intelligence,
    build_technology_fingerprints,
    match_finding_technology,
    fingerprint_ambiguity_reasons,
    finding_product_ambiguity_reasons,
    fingerprint_staleness_reasons,
)


def _graph():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "tech:nginx-a",
            "technology",
            "nginx/1.24.0",
            "httpx",
            metadata={"confidence": 0.8},
        )
    )
    graph.add(
        Observation(
            "tech:nginx-b",
            "technology",
            "nginx 1.24.0",
            "wappalyzer",
            metadata={"confidence": 0.9},
        )
    )
    graph.add(
        Observation(
            "tech:rails",
            "technology",
            "Ruby on Rails",
            "headers",
        )
    )
    return graph


def _finding(text: str):
    return SimpleNamespace(
        id="f1",
        title=text,
        summary="",
        impact="",
        remediation="",
        evidence=[],
    )


def test_versioned_technology_fingerprints_are_aggregated_by_source():
    fingerprints = build_technology_fingerprints(_graph())

    nginx = next(
        item
        for item in fingerprints
        if item.normalized_product == "nginx" and item.version == "1.24.0"
    )
    assert nginx.sources == ("httpx", "wappalyzer")
    assert nginx.confidence >= 0.8
    assert len(nginx.observation_ids) == 2


def test_unversioned_technology_remains_advisory():
    fingerprints = build_technology_fingerprints(_graph())

    rails = next(item for item in fingerprints if "ruby" in item.normalized_product)
    assert rails.version is None
    assert rails.confidence < 0.75


def test_finding_matches_observed_product_without_guessing_version():
    fingerprints = build_technology_fingerprints(_graph())
    matched = match_finding_technology(
        _finding("nginx request parsing discrepancy"),
        fingerprints,
    )

    assert len(matched) == 1
    assert matched[0].normalized_product == "nginx"
    assert matched[0].version == "1.24.0"


def test_unrelated_finding_does_not_receive_fingerprint():
    fingerprints = build_technology_fingerprints(_graph())

    assert match_finding_technology(
        _finding("GraphQL authorization discrepancy"),
        fingerprints,
    ) == ()


def test_fingerprint_intelligence_never_enables_exploitation():
    result = build_finding_fingerprint_intelligence(
        [_finding("nginx response discrepancy")],
        _graph(),
    )

    assert result["summary"]["versioned_fingerprints"] == 1
    assert result["summary"]["multi_source_fingerprints"] == 1
    assert result["summary"]["findings_with_versioned_match"] == 1
    assert result["automatic_exploitation"] is False


def test_conflicting_versions_are_marked_ambiguous():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "tech:nginx-old",
            "technology",
            "nginx/1.24.0",
            "httpx",
            metadata={"confidence": 0.9},
        )
    )
    graph.add(
        Observation(
            "tech:nginx-new",
            "technology",
            "nginx/1.25.5",
            "wappalyzer",
            metadata={"confidence": 0.9},
        )
    )
    matched = match_finding_technology(
        _finding("nginx request parsing discrepancy"),
        build_technology_fingerprints(graph),
    )

    assert fingerprint_ambiguity_reasons(matched) == (
        "conflicting_version_fingerprints",
        "single_source_version_evidence",
    )


def test_multi_source_same_version_is_not_ambiguous():
    matched = match_finding_technology(
        _finding("nginx request parsing discrepancy"),
        build_technology_fingerprints(_graph()),
    )

    assert fingerprint_ambiguity_reasons(matched) == ()


def test_declared_product_is_matched_even_when_title_is_generic():
    finding = _finding("generic parsing discrepancy")
    finding.product = "nginx"
    matched = match_finding_technology(
        finding,
        build_technology_fingerprints(_graph()),
    )

    assert any(item.normalized_product == "nginx" for item in matched)
    assert finding_product_ambiguity_reasons(
        finding,
        build_technology_fingerprints(_graph()),
    ) == ()


def test_unobserved_declared_product_is_marked_ambiguous():
    finding = _finding("generic parsing discrepancy")
    finding.product = "apache"
    fingerprints = build_technology_fingerprints(_graph())

    assert finding_product_ambiguity_reasons(
        finding,
        fingerprints,
    ) == ("declared_product_not_observed",)


def test_old_timestamped_version_is_marked_stale():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "tech:nginx-old",
            "technology",
            "nginx/1.24.0",
            "httpx",
            metadata={
                "confidence": 0.9,
                "observed_at": "2026-08-01T00:00:00+00:00",
            },
        )
    )
    matched = match_finding_technology(
        _finding("nginx parsing issue"),
        build_technology_fingerprints(graph),
    )

    assert matched[0].latest_observed_at == "2026-08-01T00:00:00+00:00"
    assert fingerprint_staleness_reasons(
        matched,
        now=datetime(2026, 10, 7, tzinfo=timezone.utc),
        max_age_days=30,
    ) == ("stale_version_fingerprints",)


def test_recent_timestamped_version_is_not_stale():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "tech:nginx-recent",
            "technology",
            "nginx/1.24.0",
            "httpx",
            metadata={
                "confidence": 0.9,
                "observed_at": "2026-10-01T00:00:00Z",
            },
        )
    )
    matched = match_finding_technology(
        _finding("nginx parsing issue"),
        build_technology_fingerprints(graph),
    )

    assert fingerprint_staleness_reasons(
        matched,
        now=datetime(2026, 10, 7, tzinfo=timezone.utc),
        max_age_days=30,
    ) == ()


def test_missing_timestamp_does_not_invent_staleness():
    matched = match_finding_technology(
        _finding("nginx parsing issue"),
        build_technology_fingerprints(_graph()),
    )

    assert fingerprint_staleness_reasons(
        matched,
        now=datetime(2026, 10, 7, tzinfo=timezone.utc),
        max_age_days=30,
    ) == ()


def test_same_asset_sources_aggregate_even_with_distinct_asset_observation_ids():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "asset:httpx",
            "asset",
            "https://example.test",
            "httpx",
        )
    )
    graph.add(
        Observation(
            "asset:wappalyzer",
            "asset",
            "https://example.test/",
            "wappalyzer",
        )
    )
    graph.add(
        Observation(
            "tech:httpx",
            "technology",
            "nginx/1.24.0",
            "httpx",
            parent_ids=("asset:httpx",),
            metadata={"confidence": 0.9},
        )
    )
    graph.add(
        Observation(
            "tech:wappalyzer",
            "technology",
            "nginx 1.24.0",
            "wappalyzer",
            parent_ids=("asset:wappalyzer",),
            metadata={"confidence": 0.9},
        )
    )

    fingerprints = build_technology_fingerprints(graph)

    assert len(fingerprints) == 1
    assert fingerprints[0].sources == ("httpx", "wappalyzer")
    assert fingerprints[0].asset_observation_ids == (
        "asset:httpx",
        "asset:wappalyzer",
    )
    assert len(fingerprints[0].asset_values) == 2


def test_finding_technology_match_is_scoped_to_its_asset():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "asset:a",
            "asset",
            "https://a.example.test",
            "recon",
        )
    )
    graph.add(
        Observation(
            "asset:b",
            "asset",
            "https://b.example.test",
            "recon",
        )
    )
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "nuclei",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "tech:a",
            "technology",
            "nginx/1.24.0",
            "httpx",
            parent_ids=("asset:a",),
            metadata={"confidence": 0.95},
        )
    )
    graph.add(
        Observation(
            "tech:b",
            "technology",
            "nginx/1.25.5",
            "httpx",
            parent_ids=("asset:b",),
            metadata={"confidence": 0.95},
        )
    )
    finding = _finding("nginx request parsing discrepancy")
    finding.asset = "https://a.example.test"

    matched = match_finding_technology(
        finding,
        build_technology_fingerprints(graph),
        graph,
    )

    assert tuple(item.version for item in matched) == ("1.24.0",)
    assert matched[0].asset_values == ("https://a.example.test",)
    assert fingerprint_ambiguity_reasons(matched) == (
        "single_source_version_evidence",
    )


def test_unscoped_legacy_fingerprint_is_not_used_when_scoped_data_exists():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "asset:a",
            "asset",
            "https://a.example.test",
            "recon",
        )
    )
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "nuclei",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "tech:scoped",
            "technology",
            "apache/2.4.62",
            "httpx",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "tech:legacy",
            "technology",
            "nginx/1.24.0",
            "legacy-import",
        )
    )
    finding = _finding("nginx request parsing discrepancy")
    finding.asset = "https://a.example.test"

    matched = match_finding_technology(
        finding,
        build_technology_fingerprints(graph),
        graph,
    )

    assert matched == ()


def test_unscoped_legacy_fingerprints_fail_closed_in_multi_asset_graph():
    graph = ObservationGraph()
    graph.add(
        Observation(
            "asset:a",
            "asset",
            "https://a.example.test",
            "recon",
        )
    )
    graph.add(
        Observation(
            "asset:b",
            "asset",
            "https://b.example.test",
            "recon",
        )
    )
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "nuclei",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "tech:legacy",
            "technology",
            "nginx/1.24.0",
            "legacy-import",
        )
    )
    finding = _finding("nginx request parsing discrepancy")
    finding.asset = "https://a.example.test"

    matched = match_finding_technology(
        finding,
        build_technology_fingerprints(graph),
        graph,
    )

    assert matched == ()


def test_unscoped_fingerprint_is_rejected_even_for_single_graph_asset():
    graph = ObservationGraph()
    graph.add(
        Observation("asset:a", "asset", "https://a.example.test", "recon")
    )
    graph.add(
        Observation(
            "tech:legacy",
            "technology",
            "nginx/1.24.0",
            "legacy-import",
        )
    )
    finding = _finding("nginx request parsing discrepancy")
    finding.asset = "https://a.example.test"

    matched = match_finding_technology(
        finding,
        build_technology_fingerprints(graph),
        graph,
    )

    assert matched == ()


def test_unscoped_legacy_fingerprint_remains_supported_without_graph_assets():
    graph = _graph()
    finding = _finding("nginx request parsing discrepancy")
    finding.asset = "https://a.example.test"

    matched = match_finding_technology(
        finding,
        build_technology_fingerprints(graph),
        graph,
    )

    assert len(matched) == 1
    assert matched[0].version == "1.24.0"
