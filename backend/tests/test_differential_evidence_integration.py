import app.worker_service as worker_service
from app.finding_intelligence import build_finding_intelligence
from app.main import Campaign, CampaignState, Finding, ProgramRules, TargetInput
from app.observation_graph import Observation, ObservationGraph, load_observation_graph
from app.red_team_decision import build_red_team_decisions
from app.storage import Storage
from app.validator import ProbeResult


def _finding(fid: str) -> Finding:
    return Finding(
        id=fid,
        title="Differential fixture",
        severity="high",
        asset="https://example.test",
        endpoint="https://example.test/search?q=private-value",
        summary="bounded fixture",
        status="validation_required",
        discovered_by="scanner-a",
    )


def _campaign(*findings: Finding) -> Campaign:
    return Campaign(
        id="differential-intelligence",
        state=CampaignState.running,
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
                max_requests_per_second=1.0,
            ),
        ),
        findings=list(findings),
    )


def test_validation_worker_persists_sanitized_differential_signal_without_confirming(tmp_path, monkeypatch):
    finding = _finding("f1")
    campaign = _campaign(finding)
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    monkeypatch.setattr(
        worker_service,
        "safe_http_probe",
        lambda _campaign, _finding: ProbeResult(
            status="observed",
            url="https://example.test/search",
            parameter_names=("q",),
            http_status=200,
            content_type="text/plain",
            body_preview="baseline",
            differential={
                "eligible": True,
                "parameter": "q",
                "baseline_status": 200,
                "marker_status": 200,
                "status_changed": False,
                "body_changed": True,
                "marker_reflected": True,
            },
        ),
    )

    worker_service.process_validation(
        {"id": "job-diff-1", "campaign_id": campaign.id, "payload": {"finding_id": finding.id}},
        store,
    )

    graph = load_observation_graph(store, campaign.id)
    validation = graph.by_kind("validation")[0]
    assert validation.metadata["differential_signal"] == "strong"
    assert validation.metadata["differential_parameter"] == "q"
    assert validation.metadata["differential_marker_reflected"] is True
    assert validation.metadata["differential_status_changed"] is False
    assert validation.metadata["differential_body_changed"] is True
    assert validation.metadata["differential_baseline_status"] == 200
    assert validation.metadata["differential_marker_status"] == 200
    assert "xbowv1-" not in str(validation.metadata)
    assert "private-value" not in str(validation.metadata)

    persisted = Campaign.model_validate(store.get_campaign(campaign.id))
    assert persisted.findings[0].status == "validation_required"
    event = next(item for item in persisted.events if item.get("type") == "independent_validation_observation")
    assert event["differential_signal"] == "strong"


def test_finding_intelligence_surfaces_differential_signal_and_summary(tmp_path, monkeypatch):
    finding = _finding("f1")
    campaign = _campaign(finding)
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    monkeypatch.setattr(
        worker_service,
        "safe_http_probe",
        lambda _campaign, _finding: ProbeResult(
            status="observed",
            url="https://example.test/search",
            parameter_names=("q",),
            http_status=200,
            differential={
                "eligible": True,
                "parameter": "q",
                "baseline_status": 200,
                "marker_status": 200,
                "status_changed": False,
                "body_changed": True,
                "marker_reflected": True,
            },
        ),
    )
    worker_service.process_validation(
        {"id": "job-diff-2", "campaign_id": campaign.id, "payload": {"finding_id": finding.id}},
        store,
    )
    persisted = Campaign.model_validate(store.get_campaign(campaign.id))
    graph = load_observation_graph(store, campaign.id)

    result = build_finding_intelligence(persisted.findings, graph)
    row = result["findings"][0]

    assert row["differential"]["signal"] == "strong"
    assert row["differential"]["marker_reflected"] is True
    assert row["differential"]["observation_ids"] == [graph.by_kind("validation")[0].id]
    assert result["summary"]["strong_differential_findings"] == 1
    assert result["summary"]["weak_differential_findings"] == 0
    assert "private-value" not in str(result)


def test_red_team_decision_prioritizes_strong_signal_inside_existing_review_work():
    findings = [_finding("f-none"), _finding("f-strong")]
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:f-none",
            "finding",
            "f-none",
            "scanner-a",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "finding:f-strong",
            "finding",
            "f-strong",
            "scanner-a",
            parent_ids=("asset:a",),
        )
    )
    graph.add(
        Observation(
            "validation:f-strong",
            "validation",
            "observed",
            "independent-http-validator",
            parent_ids=("finding:f-strong",),
            metadata={
                "finding_id": "f-strong",
                "differential_signal": "strong",
                "differential_parameter": "q",
                "differential_marker_reflected": True,
                "differential_status_changed": False,
                "differential_body_changed": True,
            },
        )
    )

    decisions = build_red_team_decisions(findings, graph)
    strengthen = next(item for item in decisions if item.kind == "strengthen_evidence")

    assert strengthen.finding_ids[:2] == ("f-strong", "f-none")
    assert strengthen.blocked_from_execution is True
    assert all(item.blocked_from_execution is True for item in decisions)
