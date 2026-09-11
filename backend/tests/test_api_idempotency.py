import pytest
from fastapi import HTTPException

from app.jobqueue import JobQueue
from app.main import (
    Campaign,
    EvidenceInput,
    Finding,
    ProgramRules,
    TargetInput,
    add_finding,
    add_text_artifact,
    validate_finding,
)
from app.observation_graph import Observation
from app.storage import Storage


def _setup(tmp_path, monkeypatch, *, findings=None):
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
                authorization_reference="test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
        findings=findings or [],
    )
    Storage(db, artifacts).save_campaign(campaign.model_dump(mode="json"))
    return db, artifacts


def _record_observed_validation(db, artifacts, finding_id="f1"):
    store = Storage(db, artifacts)
    store.put_observation("c1", Observation("a1", "asset", "example.test", "scanner").to_dict())
    store.put_observation(
        "c1",
        Observation(
            f"finding:{finding_id}",
            "finding",
            finding_id,
            "scanner",
            parent_ids=("a1",),
        ).to_dict(),
    )
    store.put_observation(
        "c1",
        Observation(
            "v1",
            "validation",
            "observed",
            "independent-http-validator",
            parent_ids=(f"finding:{finding_id}",),
        ).to_dict(),
    )


def test_duplicate_finding_retry_returns_existing_and_keeps_one_job(tmp_path, monkeypatch):
    db, _ = _setup(tmp_path, monkeypatch)
    finding = Finding(
        id="f1",
        title="candidate",
        severity="medium",
        asset="https://example.test/path",
        summary="bounded fixture",
        discovered_by="fixture",
    )

    first = add_finding("c1", finding.model_copy(deep=True))
    second = add_finding("c1", finding.model_copy(deep=True))

    assert first.id == second.id == "f1"
    stored = Storage(db).get_campaign("c1")
    assert len(stored["findings"]) == 1
    assert JobQueue(db).stats()["total"] == 1


def test_resolution_requires_observed_independent_validation(tmp_path, monkeypatch):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    db, _ = _setup(tmp_path, monkeypatch, findings=[finding])

    with pytest.raises(HTTPException) as exc:
        validate_finding("c1", "f1", True, "human-reviewer")

    assert exc.value.status_code == 409
    stored = Storage(db).get_campaign("c1")
    assert stored["findings"][0]["status"] == "validation_required"
    assert JobQueue(db).stats()["total"] == 0


def test_repeated_validation_does_not_queue_duplicate_report(tmp_path, monkeypatch):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    db, artifacts = _setup(tmp_path, monkeypatch, findings=[finding])
    _record_observed_validation(db, artifacts)

    first = validate_finding("c1", "f1", True, "human-reviewer")
    second = validate_finding("c1", "f1", True, "human-reviewer")

    assert first.status == second.status == "confirmed"
    assert JobQueue(db).stats()["total"] == 1


def test_self_sourced_observation_cannot_unlock_resolution(tmp_path, monkeypatch):
    finding = Finding(
        id="f1",
        title="candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        status="validation_required",
        discovered_by="scanner",
    )
    db, artifacts = _setup(tmp_path, monkeypatch, findings=[finding])
    store = Storage(db, artifacts)
    store.put_observation("c1", Observation("a1", "asset", "example.test", "scanner").to_dict())
    store.put_observation(
        "c1",
        Observation("finding:f1", "finding", "f1", "scanner", parent_ids=("a1",)).to_dict(),
    )
    store.put_observation(
        "c1",
        Observation("v1", "validation", "observed", "scanner", parent_ids=("finding:f1",)).to_dict(),
    )

    with pytest.raises(HTTPException) as exc:
        validate_finding("c1", "f1", False, "human-reviewer")

    assert exc.value.status_code == 409
    assert Storage(db).get_campaign("c1")["findings"][0]["status"] == "validation_required"


def test_duplicate_text_artifact_retry_reuses_artifact_and_event(tmp_path, monkeypatch):
    db, artifacts = _setup(tmp_path, monkeypatch)
    evidence = EvidenceInput(kind="http_evidence", content="same evidence", media_type="text/plain")

    first = add_text_artifact("c1", evidence)
    second = add_text_artifact("c1", evidence)

    assert first["id"] == second["id"]
    store = Storage(db, artifacts)
    assert len(store.list_artifacts("c1")) == 1
    campaign = store.get_campaign("c1")
    events = [event for event in campaign["events"] if event.get("type") == "artifact_stored"]
    assert len(events) == 1


def test_completed_campaign_rejects_new_findings(tmp_path, monkeypatch):
    db, artifacts = _setup(tmp_path, monkeypatch)
    store = Storage(db, artifacts)
    document, version = store.get_campaign_record("c1")
    document["state"] = "completed"
    store.save_campaign(document, expected_version=version)

    candidate = Finding(
        id="f-new",
        title="new candidate",
        severity="low",
        asset="https://example.test",
        summary="fixture",
        discovered_by="scanner",
    )

    with pytest.raises(HTTPException) as exc:
        add_finding("c1", candidate)

    assert exc.value.status_code == 409
    assert "completed" in str(exc.value.detail)
    assert Storage(db).get_campaign("c1")["findings"] == []
    assert JobQueue(db).stats()["total"] == 0
