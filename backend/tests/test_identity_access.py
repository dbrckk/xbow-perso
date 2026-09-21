from app.main import app
from app.identity_access import (
    build_identity_access_differentials,
    summarize_identity_access_differentials,
)
from app.observation_graph import Observation, ObservationGraph


def _access(identity, endpoint, status, digest):
    return Observation(
        f"access:{identity}:{endpoint}",
        "access_surface",
        endpoint,
        "browser",
        metadata={
            "identity_label": identity,
            "http_status": status,
            "content_sha256": digest,
        },
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
