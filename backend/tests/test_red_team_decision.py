from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.red_team_decision import build_red_team_decisions, campaign_red_team_decisions
from app.storage import Storage


def test_decision_engine_prioritizes_scope_integrity():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "endpoint:e",
            "endpoint",
            "https://outside.test/account?id=secret",
            "recon",
            parent_ids=("asset:a",),
        )
    )

    decisions = build_red_team_decisions(
        [],
        graph,
        scope_checker=lambda host: host == "example.test",
    )

    assert decisions[0].kind == "scope_integrity"
    assert decisions[0].priority == 1.0
    assert decisions[0].blocked_from_execution is True
    assert "secret" not in str([item.to_dict() for item in decisions])


def test_decision_engine_prioritizes_validation_and_evidence():
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("asset:a",),
        )
    )
    finding = Finding(
        id="f1",
        title="fixture",
        severity="critical",
        asset="https://example.test",
        summary="bounded fixture",
        status="validation_required",
        discovered_by="scanner",
    )

    decisions = build_red_team_decisions([finding], graph)

    kinds = [item.kind for item in decisions]
    assert kinds[0] == "validate_findings"
    assert "strengthen_evidence" in kinds
    assert all(item.blocked_from_execution is True for item in decisions)


def test_decision_engine_becomes_idle_when_no_work_exists():
    decisions = build_red_team_decisions([], ObservationGraph())

    assert len(decisions) == 1
    assert decisions[0].kind == "idle"
    assert decisions[0].priority == 0.0


def test_decision_route_is_exposed_and_scope_aware(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="decision-1",
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
    store.put_observation(
        campaign.id,
        Observation("asset:a", "asset", "example.test", "recon").to_dict(),
    )

    result = campaign_red_team_decisions(campaign.id)

    assert "/api/campaigns/{campaign_id}/red-team-decisions" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["advisory_only"] is True
    assert result["scope_aware"] is True


def test_decision_limit_fails_closed():
    graph = ObservationGraph()

    for invalid in (0, 26):
        try:
            build_red_team_decisions([], graph, limit=invalid)
        except ValueError as exc:
            assert "between 1 and 25" in str(exc)
        else:
            raise AssertionError("invalid decision limit should fail")



def _strong_finding_graph():
    graph = ObservationGraph()
    graph.add(Observation("asset:strong", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:strong",
            "finding",
            "strong",
            "scanner-a",
            parent_ids=("asset:strong",),
        )
    )
    graph.add(
        Observation(
            "validation:strong",
            "validation",
            "observed",
            "validator-b",
            parent_ids=("finding:strong",),
        )
    )
    graph.add(
        Observation(
            "evidence:strong",
            "evidence",
            "artifact-reference",
            "validator-c",
            parent_ids=("validation:strong",),
            metadata={
                "artifact_id": "artifact-strong",
                "artifact_kind": "validation",
                "artifact_sha256": "c" * 64,
            },
        )
    )
    return graph


def test_readiness_suppresses_redundant_validation_when_report_ready():
    finding = Finding(
        id="strong",
        title="fixture",
        severity="high",
        asset="https://example.test",
        summary="bounded fixture",
        status="validation_required",
        discovered_by="scanner-a",
    )
    snapshots = [
        {
            "graph_fingerprint": "stable-1",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "strong",
                    "confidence": 0.95,
                    "status": "supported",
                }
            ],
        }
    ]

    decisions = build_red_team_decisions(
        [finding],
        _strong_finding_graph(),
        hypothesis_snapshots=snapshots,
    )
    kinds = [item.kind for item in decisions]

    assert "validate_findings" not in kinds
    assert "review_for_report" in kinds


def test_contradictory_readiness_requires_human_review():
    finding = Finding(
        id="strong",
        title="fixture",
        severity="high",
        asset="https://example.test",
        summary="bounded fixture",
        status="validation_required",
        discovered_by="scanner-a",
    )
    snapshots = [
        {
            "graph_fingerprint": "c",
            "created_at": "2026-09-14T09:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "strong",
                    "confidence": 0.75,
                    "status": "partially_supported",
                }
            ],
        },
        {
            "graph_fingerprint": "b",
            "created_at": "2026-09-14T08:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "strong",
                    "confidence": 0.95,
                    "status": "supported",
                }
            ],
        },
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "strong",
                    "confidence": 0.35,
                    "status": "unvalidated",
                }
            ],
        },
    ]

    decisions = build_red_team_decisions(
        [finding],
        _strong_finding_graph(),
        hypothesis_snapshots=snapshots,
    )

    assert decisions[0].kind == "review_contradiction"
    assert decisions[0].priority == 0.98
    assert decisions[0].finding_ids == ("strong",)



def _cluster_findings():
    first = Finding(
        id="cluster-ready",
        title="Reflected script injection",
        severity="high",
        asset="https://example.test",
        endpoint="https://example.test/account?id=one",
        summary="bounded fixture",
        cwe="CWE-79",
        status="validation_required",
        discovered_by="scanner-a",
    )
    second = Finding(
        id="cluster-weak",
        title="Reflected script injection",
        severity="high",
        asset="https://example.test",
        endpoint="https://example.test/account?id=two",
        summary="bounded fixture",
        cwe="CWE-79",
        status="validation_required",
        discovered_by="scanner-a",
    )
    return first, second


def _mixed_cluster_graph():
    graph = ObservationGraph()
    graph.add(Observation("asset:cluster", "asset", "example.test", "recon"))
    for fid in ("cluster-ready", "cluster-weak"):
        graph.add(
            Observation(
                f"finding:{fid}",
                "finding",
                fid,
                "scanner-a",
                parent_ids=("asset:cluster",),
            )
        )
    graph.add(
        Observation(
            "validation:cluster-ready",
            "validation",
            "observed",
            "validator-b",
            parent_ids=("finding:cluster-ready",),
        )
    )
    graph.add(
        Observation(
            "evidence:cluster-ready",
            "evidence",
            "artifact-reference",
            "validator-c",
            parent_ids=("validation:cluster-ready",),
            metadata={
                "artifact_id": "artifact-cluster-ready",
                "artifact_kind": "validation",
                "artifact_sha256": "d" * 64,
            },
        )
    )
    return graph


def test_mixed_cluster_holds_ready_member_back_from_report_review():
    ready, weak = _cluster_findings()
    snapshots = [
        {
            "graph_fingerprint": "cluster-a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "cluster-ready",
                    "confidence": 0.95,
                    "status": "supported",
                },
                {
                    "finding_id": "cluster-weak",
                    "confidence": 0.35,
                    "status": "unvalidated",
                },
            ],
        }
    ]

    decisions = build_red_team_decisions(
        [ready, weak],
        _mixed_cluster_graph(),
        hypothesis_snapshots=snapshots,
    )

    report = next(
        (item for item in decisions if item.kind == "review_for_report"),
        None,
    )
    validate = next(item for item in decisions if item.kind == "validate_findings")

    assert report is None or "cluster-ready" not in report.finding_ids
    assert "cluster-weak" in validate.finding_ids
    assert "cluster-ready" not in validate.finding_ids


def test_blocked_cluster_escalates_all_cluster_members_for_human_review():
    ready, weak = _cluster_findings()
    graph = _mixed_cluster_graph()
    snapshots = [
        {
            "graph_fingerprint": "c",
            "created_at": "2026-09-14T09:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "cluster-ready",
                    "confidence": 0.75,
                    "status": "partially_supported",
                },
                {
                    "finding_id": "cluster-weak",
                    "confidence": 0.35,
                    "status": "unvalidated",
                },
            ],
        },
        {
            "graph_fingerprint": "b",
            "created_at": "2026-09-14T08:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "cluster-ready",
                    "confidence": 0.95,
                    "status": "supported",
                },
                {
                    "finding_id": "cluster-weak",
                    "confidence": 0.35,
                    "status": "unvalidated",
                },
            ],
        },
        {
            "graph_fingerprint": "a",
            "created_at": "2026-09-14T07:00:00+00:00",
            "hypotheses": [
                {
                    "finding_id": "cluster-ready",
                    "confidence": 0.35,
                    "status": "unvalidated",
                },
                {
                    "finding_id": "cluster-weak",
                    "confidence": 0.35,
                    "status": "unvalidated",
                },
            ],
        },
    ]

    decisions = build_red_team_decisions(
        [ready, weak],
        graph,
        hypothesis_snapshots=snapshots,
    )

    review = decisions[0]
    assert review.kind == "review_contradiction"
    assert set(review.finding_ids) == {"cluster-ready", "cluster-weak"}
