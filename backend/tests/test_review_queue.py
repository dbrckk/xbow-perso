from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.review_queue import build_review_queue, campaign_review_queue
from app.storage import Storage


def test_review_queue_prioritizes_validation_gap_over_surface_review():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=secret",
            "scanner",
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

    tasks = build_review_queue(graph)

    assert tasks[0].kind == "validate_finding"
    assert tasks[0].priority > tasks[1].priority
    assert all(item.priority <= 1.0 for item in tasks)
    assert "secret" not in str([item.to_dict() for item in tasks])


def test_review_queue_is_bounded_and_deterministic():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    for index in range(5):
        graph.add(
            Observation(
                f"endpoint:{index}",
                "endpoint",
                f"https://example.test/account/{index}?id={index}",
                "recon",
                parent_ids=("asset:a",),
            )
        )

    first = build_review_queue(graph, limit=3)
    second = build_review_queue(graph, limit=3)

    assert len(first) == 3
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]


def test_review_queue_route_is_exposed_and_advisory(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="review-1",
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

    result = campaign_review_queue(campaign.id)

    assert "/api/campaigns/{campaign_id}/review-queue" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["advisory_only"] is True


def test_review_queue_rejects_unbounded_limits():
    graph = ObservationGraph()

    for invalid in (0, 101):
        try:
            build_review_queue(graph, limit=invalid)
        except ValueError as exc:
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("invalid review queue limit should fail")
