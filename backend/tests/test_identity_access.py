from app.main import app
from app.identity_access import (
    build_identity_access_differentials,
    summarize_identity_access_differentials,
)
from app.observation_graph import Observation, ObservationGraph


def _access(identity, endpoint, status, digest, structure=None, metrics=None):
    metadata = {
        "identity_label": identity,
        "http_status": status,
        "content_sha256": digest,
    }
    if structure is not None:
        metadata["structure_sha256"] = structure
    if metrics is not None:
        metadata["structure_metrics"] = metrics
    return Observation(
        f"access:{identity}:{endpoint}",
        "access_surface",
        endpoint,
        "browser",
        metadata=metadata,
    )


def test_identity_access_detects_status_divergence_without_claiming_vulnerability():
    graph = ObservationGraph()
    graph.add(_access("user-a", "https://example.test/admin", 403, "a" * 64))
    graph.add(_access("admin-a", "https://example.test/admin", 200, "b" * 64))

    items = build_identity_access_differentials(graph)

    assert len(items) == 1
    assert items[0].signal == "status_divergence"
    assert items[0].requires_human_review is True
    summary = summarize_identity_access_differentials(graph)
    assert summary["automatic_vulnerability_claim"] is False


def test_identity_access_detects_content_divergence_at_same_status():
    graph = ObservationGraph()
    graph.add(_access("user-a", "https://example.test/account", 200, "a" * 64))
    graph.add(_access("user-b", "https://example.test/account", 200, "b" * 64))

    items = build_identity_access_differentials(graph)

    assert items[0].signal == "content_divergence"


def test_identity_access_requires_two_explicit_test_identities():
    graph = ObservationGraph()
    graph.add(_access("user-a", "https://example.test/account", 200, "a" * 64))

    assert build_identity_access_differentials(graph) == []



def test_identity_access_differential_route_is_exposed():
    assert (
        "/api/campaigns/{campaign_id}/identity-access-differentials"
        in app.openapi()["paths"]
    )



def test_identity_access_prioritizes_structure_divergence_over_content_noise():
    graph = ObservationGraph()
    graph.add(
        _access(
            "user-a",
            "https://example.test/account",
            200,
            "a" * 64,
            "1" * 64,
            {"links": 5, "forms": 1, "buttons": 2},
        )
    )
    graph.add(
        _access(
            "user-b",
            "https://example.test/account",
            200,
            "b" * 64,
            "2" * 64,
            {"links": 9, "forms": 2, "buttons": 6},
        )
    )

    item = build_identity_access_differentials(graph)[0]

    assert item.signal == "structure_divergence"
    assert item.priority_score == 75
    assert item.structure_metrics_by_identity["user-a"]["forms"] == 1
    summary = summarize_identity_access_differentials(graph)
    assert summary["summary"]["structure_divergence"] == 1
    assert summary["network_requests_performed"] == 0
    assert summary["sensitive_content_retained"] is False


def test_identity_access_keeps_hash_only_difference_lower_priority():
    graph = ObservationGraph()
    graph.add(
        _access(
            "user-a",
            "https://example.test/feed",
            200,
            "a" * 64,
            "same" * 16,
            {"links": 8, "forms": 0},
        )
    )
    graph.add(
        _access(
            "user-b",
            "https://example.test/feed",
            200,
            "b" * 64,
            "same" * 16,
            {"links": 8, "forms": 0},
        )
    )

    item = build_identity_access_differentials(graph)[0]

    assert item.signal == "content_divergence"
    assert item.priority_score == 45
