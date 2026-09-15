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


def test_review_queue_filters_out_of_scope_work():
    graph = ObservationGraph()
    graph.add(Observation("inside", "asset", "example.test", "recon"))
    graph.add(Observation("outside", "asset", "outside.test", "recon"))
    graph.add(
        Observation(
            "inside:e",
            "endpoint",
            "https://example.test/account?id=1",
            "recon",
            parent_ids=("inside",),
        )
    )
    graph.add(
        Observation(
            "outside:e",
            "endpoint",
            "https://outside.test/admin?id=2",
            "recon",
            parent_ids=("outside",),
        )
    )

    tasks = build_review_queue(
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert tasks
    assert all(item.target.startswith("https://example.test/") for item in tasks)
    assert "outside.test" not in str([item.to_dict() for item in tasks])


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
    assert result["scope_aware"] is True


def test_review_queue_rejects_unbounded_limits():
    graph = ObservationGraph()

    for invalid in (0, 101):
        try:
            build_review_queue(graph, limit=invalid)
        except ValueError as exc:
            assert "between 1 and 100" in str(exc)
        else:
            raise AssertionError("invalid review queue limit should fail")


def test_review_queue_boosts_contradictory_hypothesis_validation():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=1",
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

    baseline = build_review_queue(graph)
    boosted = build_review_queue(
        graph,
        stability={
            "f1": {
                "finding_id": "f1",
                "stability": "contradictory",
                "stability_score": 0.2,
            }
        },
    )

    assert baseline[0].kind == "validate_finding"
    assert boosted[0].kind == "validate_finding"
    assert boosted[0].priority > baseline[0].priority
    assert "contradictory" in boosted[0].reason


def test_review_queue_evolving_hypothesis_gets_smaller_bonus():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=1",
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

    evolving = build_review_queue(
        graph,
        stability={"f1": {"finding_id": "f1", "stability": "evolving"}},
    )
    contradictory = build_review_queue(
        graph,
        stability={"f1": {"finding_id": "f1", "stability": "contradictory"}},
    )

    assert evolving[0].priority < contradictory[0].priority
    assert "evolving" in evolving[0].reason


def test_review_queue_exposes_score_components_for_validation_tasks():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=1",
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

    task = build_review_queue(
        graph,
        stability={"f1": {"finding_id": "f1", "stability": "contradictory"}},
    )[0]

    components = task.to_dict()["score_components"]
    assert set(components) == {
        "base",
        "severity",
        "confidence_gap",
        "evidence_chain_gap",
        "temporal_instability",
        "raw_total",
        "capped_total",
    }
    assert components["base"] == 0.75
    assert components["temporal_instability"] == 0.10
    assert components["raw_total"] >= task.priority
    assert components["capped_total"] == task.priority


def test_surface_review_tasks_expose_empty_score_components():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=1",
            "scanner",
            parent_ids=("asset:a",),
        )
    )

    task = next(item for item in build_review_queue(graph) if item.kind != "validate_finding")

    assert task.to_dict()["score_components"] == {}


def test_review_queue_severity_component_increases_validation_priority():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=1",
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

    info = build_review_queue(graph, severities={"f1": "info"})[0]
    critical = build_review_queue(graph, severities={"f1": "critical"})[0]

    assert critical.priority > info.priority
    assert info.score_components["severity"] == 0.00
    assert critical.score_components["severity"] == 0.12


def test_review_queue_unknown_severity_fails_closed_to_zero_bonus():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=1",
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

    task = build_review_queue(graph, severities={"f1": "unexpected"})[0]

    assert task.score_components["severity"] == 0.00



def test_review_queue_prioritizes_stale_report_for_human_review():
    task = build_review_queue(
        ObservationGraph(),
        stale_reports=[
            {
                "artifact_id": "report-1",
                "stale": True,
                "stale_reasons": [
                    "reporting_governance_changed",
                    "report_provenance_changed",
                ],
            }
        ],
    )[0]

    assert task.kind == "review_stale_report"
    assert task.target == "report-1"
    assert task.priority == 0.92
    assert "human re-review is required" in task.reason
    assert "reporting_governance_changed" in task.reason
    assert task.evidence_ids == ()
    assert task.score_components["governance_drift"] == 1.0


def test_review_queue_ignores_fresh_reports():
    tasks = build_review_queue(
        ObservationGraph(),
        stale_reports=[
            {
                "artifact_id": "report-1",
                "fresh": True,
                "stale": False,
                "stale_reasons": [],
            }
        ],
    )

    assert tasks == []



def test_review_queue_deduplicates_same_stale_report():
    tasks = build_review_queue(
        ObservationGraph(),
        stale_reports=[
            {
                "artifact_id": "report-1",
                "stale": True,
                "stale_reasons": ["reporting_governance_changed"],
            },
            {
                "artifact_id": "report-1",
                "stale": True,
                "stale_reasons": ["report_provenance_changed"],
            },
        ],
    )

    matching = [
        item
        for item in tasks
        if item.kind == "review_stale_report" and item.target == "report-1"
    ]
    assert len(matching) == 1



def test_review_task_identity_is_deterministic_and_order_independent():
    stale = {
        "artifact_id": "report-identity",
        "stale": True,
        "stale_reasons": ["reporting_governance_changed"],
    }
    first = build_review_queue(
        ObservationGraph(),
        stale_reports=[stale],
    )[0]
    second = build_review_queue(
        ObservationGraph(),
        stale_reports=[dict(stale)],
    )[0]

    assert first.task_id == second.task_id
    assert len(first.task_id) == 64
    assert first.to_dict()["task_id"] == first.task_id


def test_review_task_identity_changes_for_distinct_report():
    first = build_review_queue(
        ObservationGraph(),
        stale_reports=[
            {
                "artifact_id": "report-a",
                "stale": True,
                "stale_reasons": ["reporting_governance_changed"],
            }
        ],
    )[0]
    second = build_review_queue(
        ObservationGraph(),
        stale_reports=[
            {
                "artifact_id": "report-b",
                "stale": True,
                "stale_reasons": ["reporting_governance_changed"],
            }
        ],
    )[0]

    assert first.task_id != second.task_id



def test_review_queue_snapshot_is_order_independent():
    first = build_review_queue(
        ObservationGraph(),
        stale_reports=[
            {
                "artifact_id": "report-a",
                "stale": True,
                "stale_reasons": ["reporting_governance_changed"],
            },
            {
                "artifact_id": "report-b",
                "stale": True,
                "stale_reasons": ["report_provenance_changed"],
            },
        ],
    )
    second = list(reversed(first))

    snapshot_a = review_queue_snapshot(first)
    snapshot_b = review_queue_snapshot(second)

    assert snapshot_a["fingerprint"] == snapshot_b["fingerprint"]
    assert snapshot_a["task_ids"] == snapshot_b["task_ids"]
    assert snapshot_a["task_count"] == 2
    assert snapshot_a["by_kind"]["review_stale_report"] == 2
    assert snapshot_a["read_only"] is True
    assert snapshot_a["advisory_only"] is True


def test_review_queue_snapshot_changes_when_logical_task_set_changes():
    one = build_review_queue(
        ObservationGraph(),
        stale_reports=[
            {
                "artifact_id": "report-a",
                "stale": True,
                "stale_reasons": ["reporting_governance_changed"],
            }
        ],
    )
    two = build_review_queue(
        ObservationGraph(),
        stale_reports=[
            {
                "artifact_id": "report-a",
                "stale": True,
                "stale_reasons": ["reporting_governance_changed"],
            },
            {
                "artifact_id": "report-b",
                "stale": True,
                "stale_reasons": ["reporting_governance_changed"],
            },
        ],
    )

    assert (
        review_queue_snapshot(one)["fingerprint"]
        != review_queue_snapshot(two)["fingerprint"]
    )
