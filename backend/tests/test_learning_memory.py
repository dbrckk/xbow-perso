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


def test_worker_summary_counts_one_final_state_per_job():
    from app.learning_memory import summarize_worker_outcomes

    def event(status, *, job_id="job-1", kind="nuclei_scan"):
        return {
            "type": "worker_outcome",
            "job_id": job_id,
            "job_kind": kind,
            "status": status,
            "success": status == "completed",
            "attempts": 1,
        }

    summary = summarize_worker_outcomes(
        [
            event("queued"),
            event("queued"),
            event("failed"),
            event("completed"),
            event("failed", job_id="job-2"),
        ]
    )

    assert summary["totals"] == {
        "completed": 1,
        "failed": 1,
        "cancelled": 0,
        "requeued": 0,
    }
    assert summary["by_job_kind"]["nuclei_scan"]["completed"] == 1
    assert summary["distinct_jobs"] == 2
    assert summary["duplicate_events"] == 3
    assert len(summary["recent_outcomes"]) == 5
    assert summary["contains_job_payloads"] is False


def test_worker_summary_does_not_merge_different_job_kinds():
    from app.learning_memory import summarize_worker_outcomes

    summary = summarize_worker_outcomes([
        {
            "type": "worker_outcome",
            "job_id": "shared-id",
            "job_kind": kind,
            "status": "completed",
            "attempts": 1,
        }
        for kind in ("nuclei_scan", "recon_task")
    ])

    assert summary["distinct_jobs"] == 2
    assert summary["totals"]["completed"] == 2


def test_invalid_worker_events_cannot_inflate_recovery_failure_counts():
    from app.learning_memory import summarize_worker_outcomes

    events = [
        {
            "type": "worker_outcome",
            "job_id": "",
            "job_kind": "nuclei_scan",
            "status": "failed",
            "attempts": 1,
        },
        {
            "type": "worker_outcome",
            "job_id": "job-1",
            "job_kind": "nuclei_scan",
            "status": "failed",
            "attempts": "invalid",
        },
        {
            "type": "worker_outcome",
            "job_id": "job-1",
            "job_kind": "nuclei_scan",
            "status": "failed",
            "attempts": 6,
        },
        {
            "type": "worker_outcome",
            "job_id": "job-1",
            "job_kind": "nuclei_scan",
            "status": "completed",
            "attempts": 2,
        },
    ]
    summary = summarize_worker_outcomes(events)

    assert summary["totals"]["failed"] == 0
    assert summary["totals"]["completed"] == 1
    assert summary["distinct_jobs"] == 1
    assert summary["duplicate_events"] == 0


def test_no_finding_feedback_uses_final_worker_state_not_retry_event_count():
    from app.learning_memory import summarize_worker_outcomes
    from app.no_finding_recovery import build_no_finding_recovery

    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "inventory"))
    graph.add(Observation(
        "scan:one",
        "evidence",
        "scan-complete",
        "nuclei",
        parent_ids=("asset:a",),
        metadata={
            "phase": "scan",
            "status": "completed",
            "job_id": "job-1",
        },
    ))
    events = [
        {
            "type": "worker_outcome",
            "job_id": "job-1",
            "job_kind": "nuclei_scan",
            "status": status,
            "attempts": 1,
        }
        for status in ("queued", "queued", "completed")
    ]
    outcomes = summarize_worker_outcomes(events)
    feedback = build_no_finding_recovery(
        graph,
        scope_checker=lambda host: host == "example.test",
        available_task_kinds=("crawl",),
        worker_outcomes=outcomes,
    )

    assert outcomes["totals"]["completed"] == 1
    assert outcomes["totals"]["requeued"] == 0
    assert feedback.state == "recovery_advisory"
    assert feedback.recommended_task_kinds == ("crawl",)


def test_technique_memory_deduplicates_evidence_from_one_worker_job():
    graph = ObservationGraph()
    for index, source in enumerate(("scanner-a", "scanner-b", "scanner-b")):
        graph.add(
            Observation(
                f"evidence:{index}",
                "evidence",
                "same-job-outcome",
                source,
                metadata={
                    "technique": "scanner:nuclei",
                    "outcome": "success",
                    "job_id": "job-1",
                },
            )
        )
    memory = build_learning_memory(graph)[0]

    assert memory.attempts == 1
    assert memory.successes == 1
    assert memory.failures == 0
    assert memory.source_count == 1
    assert memory.confidence == 0.1


def test_technique_memory_conflicting_job_outcomes_are_inconclusive():
    graph = ObservationGraph()
    for index, outcome in enumerate(("failure", "success", "failure")):
        graph.add(
            Observation(
                f"evidence:{index}",
                "evidence",
                "conflicting-job-outcome",
                "scanner-a",
                metadata={
                    "technique": "scanner:nuclei",
                    "outcome": outcome,
                    "job_id": "job-1",
                },
            )
        )
    memory = build_learning_memory(graph)[0]

    assert memory.attempts == 1
    assert memory.successes == 0
    assert memory.failures == 0
    assert memory.inconclusive == 1
    assert memory.confidence == 0.0


def test_technique_memory_keeps_independent_jobs_and_techniques_distinct():
    graph = ObservationGraph()
    for index, (technique, job_id) in enumerate((
        ("scanner:nuclei", "shared-job"),
        ("scanner:nuclei", "other-job"),
        ("scanner:strix", "shared-job"),
    )):
        graph.add(
            Observation(
                f"evidence:{index}",
                "evidence",
                "job-result",
                "scanner-a",
                metadata={
                    "technique": technique,
                    "outcome": "success",
                    "job_id": job_id,
                },
            )
        )
    memories = {item.technique: item for item in build_learning_memory(graph)}

    assert memories["scanner:nuclei"].attempts == 2
    assert memories["scanner:nuclei"].successes == 2
    assert memories["scanner:strix"].attempts == 1


def test_technique_memory_ignores_invalid_explicit_job_identifiers():
    graph = ObservationGraph()
    for index, job_id in enumerate(("", None, 123, "x" * 129)):
        graph.add(
            Observation(
                f"evidence:invalid:{index}",
                "evidence",
                "invalid-job-result",
                "scanner-a",
                metadata={
                    "technique": "scanner:nuclei",
                    "outcome": "success",
                    "job_id": job_id,
                },
            )
        )
    assert build_learning_memory(graph) == []


def test_technique_memory_preserves_legacy_evidence_without_job_identifiers():
    graph = ObservationGraph()
    for index in range(3):
        graph.add(
            Observation(
                f"legacy:{index}",
                "evidence",
                "legacy-result",
                "validator-a",
                metadata={"technique": "form-review", "outcome": "failure"},
            )
        )
    memory = build_learning_memory(graph)[0]

    assert memory.attempts == 3
    assert memory.failures == 3
    assert memory.source_count == 1
