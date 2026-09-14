from app.finding_triage import build_finding_triage, campaign_finding_triage
from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.observation_graph import Observation, ObservationGraph
from app.storage import Storage


def _finding(finding_id: str, severity: str, *, endpoint: str | None = None, cwe: str | None = None):
    return Finding(
        id=finding_id,
        title=f"fixture-{finding_id}",
        severity=severity,
        asset="https://example.test",
        endpoint=endpoint,
        summary="bounded fixture",
        cwe=cwe,
        status="validation_required",
        discovered_by="scanner",
    )


def test_triage_prioritizes_critical_unvalidated_finding():
    findings = [
        _finding("low", "low"),
        _finding("critical", "critical"),
    ]
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    for finding in findings:
        graph.add(
            Observation(
                f"finding:{finding.id}",
                "finding",
                finding.id,
                "scanner",
                parent_ids=("asset:a",),
            )
        )

    triage = build_finding_triage(findings, graph)

    assert [item.finding_id for item in triage] == ["critical", "low"]
    assert triage[0].recommended_state == "validate"
    assert triage[0].score > triage[1].score


def test_triage_marks_duplicate_candidates_without_merging():
    endpoint = "https://example.test/api?id=secret"
    findings = [
        _finding("f1", "high", endpoint=endpoint, cwe="CWE-200"),
        _finding("f2", "high", endpoint="HTTPS://EXAMPLE.TEST:443/api?id=other", cwe="cwe-200"),
    ]
    graph = ObservationGraph()

    triage = build_finding_triage(findings, graph)

    assert all(item.duplicate_candidate for item in triage)
    assert all(item.duplicate_group_size == 2 for item in triage)
    assert all(item.recommended_state == "review_duplicate" for item in triage)
    assert "secret" not in str([item.to_dict() for item in triage])
    assert "other" not in str([item.to_dict() for item in triage])


def test_triage_resolves_only_terminal_finding_with_complete_chain():
    finding = _finding("f1", "high")
    finding.status = "confirmed"
    finding.validated_by = "independent-validator"
    graph = ObservationGraph()
    graph.add(Observation("asset:a", "asset", "example.test", "scanner"))
    graph.add(Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("asset:a",)))
    graph.add(
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        )
    )
    graph.add(
        Observation(
            "evidence:x1",
            "evidence",
            "artifact-reference",
            "independent-validator",
            parent_ids=("validation:v1",),
        )
    )

    triage = build_finding_triage([finding], graph)

    assert triage[0].evidence_chain_complete is True
    assert triage[0].recommended_state == "resolved"


def test_finding_triage_route_is_exposed(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="triage-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[_finding("f1", "medium")],
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    result = campaign_finding_triage(campaign.id)

    assert "/api/campaigns/{campaign_id}/finding-triage" in app.openapi()["paths"]
    assert result["campaign_id"] == campaign.id
    assert result["read_only"] is True
    assert result["advisory_only"] is True



def test_triage_requires_high_quality_evidence_before_report_review():
    finding = _finding("quality", "high")
    graph = ObservationGraph()
    graph.add(Observation("asset:q", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:quality",
            "finding",
            "quality",
            "scanner",
            parent_ids=("asset:q",),
        )
    )
    graph.add(
        Observation(
            "validation:q",
            "validation",
            "observed",
            "validator",
            parent_ids=("finding:quality",),
        )
    )
    graph.add(
        Observation(
            "evidence:q",
            "evidence",
            "plain-reference",
            "validator",
            parent_ids=("validation:q",),
        )
    )

    triage = build_finding_triage([finding], graph)[0]

    assert triage.evidence_chain_complete is True
    assert triage.confidence >= 0.75
    assert triage.corroborated is True
    assert triage.evidence_quality_grade == "medium"
    assert triage.evidence_quality_score < 0.80
    assert triage.recommended_state == "validate"


def test_triage_allows_report_review_with_high_quality_artifact_backed_evidence():
    finding = _finding("quality-high", "high")
    graph = ObservationGraph()
    graph.add(Observation("asset:h", "asset", "example.test", "recon"))
    graph.add(
        Observation(
            "finding:quality-high",
            "finding",
            "quality-high",
            "scanner",
            parent_ids=("asset:h",),
        )
    )
    graph.add(
        Observation(
            "validation:h",
            "validation",
            "observed",
            "validator-a",
            parent_ids=("finding:quality-high",),
        )
    )
    graph.add(
        Observation(
            "evidence:h",
            "evidence",
            "artifact-reference",
            "validator-b",
            parent_ids=("validation:h",),
            metadata={"artifact_id": "artifact-h", "artifact_kind": "validation"},
        )
    )

    triage = build_finding_triage([finding], graph)[0]

    assert triage.evidence_quality_grade == "high"
    assert triage.evidence_quality_score == 1.0
    assert triage.recommended_state == "review_for_report"
