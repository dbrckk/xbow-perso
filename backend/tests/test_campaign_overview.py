from app.campaign_overview import campaign_overview
from app.main import Campaign, Finding, ProgramRules, TargetInput, app
from app.observation_graph import Observation
from app.storage import Storage


def _setup(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = Campaign(
        id="c1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=[
            Finding(
                id="f1",
                title="fixture",
                severity="medium",
                asset="https://example.test",
                summary="bounded fixture",
                status="validation_required",
                discovered_by="scanner",
            )
        ],
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    return campaign, store


def test_overview_route_is_exposed():
    assert "/api/campaigns/{campaign_id}/overview" in app.openapi()["paths"]


def test_overview_aggregates_findings_jobs_validation_and_budget(tmp_path, monkeypatch):
    campaign, store = _setup(tmp_path, monkeypatch)
    store.put_observation(
        campaign.id,
        Observation("finding:f1", "finding", "fixture", "scanner").to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "validation:f1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        ).to_dict(),
    )

    result = campaign_overview(campaign.id)

    assert result["findings"]["total"] == 1
    assert result["findings"]["by_status"]["validation_required"] == 1
    assert result["validation"]["observed_independent"] == 1
    assert result["validation"]["unresolved"] == 0
    assert result["jobs"]["inflight"] == 0
    assert result["budget"]["blocked"] is False
    assert result["reports"]["total"] == 0
    assert result["attention_required"] is False


def test_overview_flags_unresolved_findings(tmp_path, monkeypatch):
    campaign, store = _setup(tmp_path, monkeypatch)
    store.put_observation(
        campaign.id,
        Observation("finding:f1", "finding", "fixture", "scanner").to_dict(),
    )

    result = campaign_overview(campaign.id)

    assert result["validation"]["unresolved"] == 1
    assert result["attention_required"] is True


def test_overview_surfaces_report_integrity_failure_without_exposing_bytes(tmp_path, monkeypatch):
    campaign, store = _setup(tmp_path, monkeypatch)
    artifact = store.put_artifact(campaign.id, "report", b"report", media_type="text/markdown")
    metadata = store.get_artifact(campaign.id, artifact["id"])
    assert metadata is not None
    (store.artifact_root / metadata["relative_path"]).write_bytes(b"tampered")

    result = campaign_overview(campaign.id)

    assert result["reports"]["total"] == 1
    assert result["reports"]["verified"] == 0
    assert result["reports"]["integrity_errors"] == 1
    assert result["attention_required"] is True
