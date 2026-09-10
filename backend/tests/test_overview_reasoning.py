from app.campaign_overview import campaign_overview
from app.main import Campaign, Finding, ProgramRules, TargetInput
from app.observation_graph import Observation
from app.storage import Storage


def _campaign():
    return Campaign(
        id="reasoning-1",
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
                severity="high",
                asset="https://example.test",
                endpoint="https://example.test/account?id=1",
                summary="bounded fixture",
                status="validation_required",
                discovered_by="scanner",
            )
        ],
    )


def test_overview_surfaces_hypothesis_and_evidence_chain_state(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = _campaign()
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    store.put_observation(campaign.id, Observation("asset:a", "asset", "example.test", "scanner").to_dict())
    store.put_observation(
        campaign.id,
        Observation(
            "endpoint:e",
            "endpoint",
            "https://example.test/account?id=secret",
            "scanner",
            parent_ids=("asset:a",),
        ).to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "finding:f1",
            "finding",
            "f1",
            "scanner",
            parent_ids=("endpoint:e",),
        ).to_dict(),
    )

    result = campaign_overview(campaign.id)

    assert result["hypotheses"]["total"] == 3
    assert result["hypotheses"]["by_kind"] == {
        "authorization_surface_review": 1,
        "input_surface_review": 1,
        "validation_gap": 1,
    }
    assert result["hypotheses"]["highest_confidence"] == 0.9
    assert result["hypotheses"]["read_only"] is True
    assert result["evidence_chains"] == {
        "total": 1,
        "complete": 0,
        "incomplete": 1,
        "read_only": True,
    }
    assert result["correlations"] == {
        "groups": 1,
        "duplicate_groups": 0,
        "findings_in_duplicate_groups": 0,
        "auto_merge": False,
        "read_only": True,
    }
    assert "secret" not in str(result["hypotheses"])


def test_overview_chain_becomes_complete_after_independent_evidence(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = _campaign()
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    store.put_observation(campaign.id, Observation("asset:a", "asset", "example.test", "scanner").to_dict())
    store.put_observation(
        campaign.id,
        Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("asset:a",)).to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "validation:v1",
            "validation",
            "observed",
            "independent-validator",
            parent_ids=("finding:f1",),
        ).to_dict(),
    )
    store.put_observation(
        campaign.id,
        Observation(
            "evidence:x1",
            "evidence",
            "artifact-reference",
            "independent-validator",
            parent_ids=("validation:v1",),
        ).to_dict(),
    )

    result = campaign_overview(campaign.id)

    assert result["evidence_chains"]["complete"] == 1
    assert result["evidence_chains"]["incomplete"] == 0
    assert result["hypotheses"]["by_kind"].get("validation_gap", 0) == 0


def test_overview_counts_duplicate_candidate_groups(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)
    campaign = _campaign()
    campaign.findings[0].cwe = "CWE-79"
    campaign.findings.append(
        Finding(
            id="f2",
            title="duplicate candidate",
            severity="medium",
            asset="https://EXAMPLE.test:443",
            endpoint="https://example.test/account?id=2",
            summary="bounded duplicate fixture",
            cwe="cwe-79",
            status="validation_required",
            discovered_by="scanner-2",
        )
    )
    store = Storage(db, artifacts)
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    result = campaign_overview(campaign.id)

    assert result["correlations"]["groups"] == 1
    assert result["correlations"]["duplicate_groups"] == 1
    assert result["correlations"]["findings_in_duplicate_groups"] == 2
    assert result["correlations"]["auto_merge"] is False
