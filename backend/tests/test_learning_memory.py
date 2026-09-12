from app.learning_memory import build_learning_memory, campaign_learning_memory
from app.main import Campaign, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def test_learning_memory_aggregates_only_explicit_outcomes():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "evidence:1",
            "evidence",
            "review-1",
            "validator-a",
            parent_ids=("asset:a",),
            metadata={"technique": "authorization-review", "outcome": "success"},
        )
    )
    graph.add(
        Observation(
            "evidence:2",
            "evidence",
            "review-2",
            "validator-b",
            parent_ids=("asset:a",),
            metadata={"technique": "authorization-review", "outcome": "failure"},
        )
    )
    graph.add(
        Observation(
            "evidence:3",
            "evidence",
            "ignored",
            "validator-b",
            parent_ids=("asset:a",),
            metadata={"technique": "authorization-review"},
        )
    )

    memories = build_learning_memory(graph)

    assert len(memories) == 1
    memory = memories[0]
    assert memory.technique == "authorization-review"
    assert memory.attempts == 2
    assert memory.successes == 1
    assert memory.failures == 1
    assert memory.success_rate == 0.5
    assert memory.source_count == 2


def test_learning_memory_is_bounded_and_deterministic():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    for index in range(4):
        graph.add(
            Observation(
                f"evidence:{index}",
                "evidence",
                f"review-{index}",
                "validator",
                parent_ids=("asset:a",),
                metadata={"technique": f"technique-{index}", "outcome": "success"},
            )
        )

    first = build_learning_memory(graph, limit=2)
    second = build_learning_memory(graph, limit=2)

    assert len(first) == 2
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]


def test_learning_memory_route_is_exposed(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="learning-1",
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

    result = campaign_learning_memory(campaign.id)

    assert "/api/campaigns/{campaign_id}/learning-memory" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["evidence_backed"] is True


def test_learning_memory_rejects_unbounded_limits():
    graph = ObservationGraph()
    for invalid in (0, 101):
        try:
            build_learning_memory(graph, limit=invalid)
        except ValueError as exc:
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("invalid learning memory limit should fail")


def test_worker_outcome_memory_excludes_payloads_and_errors():
    from app.learning_memory import summarize_worker_outcomes, worker_outcome_event

    event = worker_outcome_event(
        {
            "id": "job-1",
            "kind": "recon_task",
            "attempts": 2,
            "payload": {"secret": "must-not-be-recorded"},
            "last_error": "sensitive detail",
        },
        success=False,
        status="queued",
    )

    assert "payload" not in event
    assert "last_error" not in event
    summary = summarize_worker_outcomes([{**event, "at": "t1"}])
    assert summary["totals"]["requeued"] == 1
    assert summary["by_job_kind"]["recon_task"]["requeued"] == 1
    assert summary["contains_job_payloads"] is False
    assert "must-not-be-recorded" not in str(summary)
    assert "sensitive detail" not in str(summary)


def test_worker_outcome_memory_rejects_unknown_kinds_and_unbounded_limits():
    from app.learning_memory import summarize_worker_outcomes, worker_outcome_event

    try:
        worker_outcome_event(
            {"id": "job-1", "kind": "shell", "attempts": 1},
            success=False,
            status="failed",
        )
    except ValueError as exc:
        assert "unsupported job kind" in str(exc)
    else:
        raise AssertionError("unknown worker outcome kinds must fail closed")

    try:
        summarize_worker_outcomes([], recent_limit=201)
    except ValueError as exc:
        assert "recent_limit" in str(exc)
    else:
        raise AssertionError("unbounded outcome history must fail closed")
