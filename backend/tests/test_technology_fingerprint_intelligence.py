from types import SimpleNamespace

from app.observation_graph import Observation, ObservationGraph
from app.technology_fingerprint_intelligence import (
    build_finding_fingerprint_intelligence,
    build_technology_fingerprints,
    match_finding_technology,
    fingerprint_ambiguity_reasons,
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
