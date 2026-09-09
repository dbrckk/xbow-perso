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
    db, _ = _setup(tmp_path, monkeypatch, findings=[finding])

    first = validate_finding("c1", "f1", True, "human-reviewer")
    second = validate_finding("c1", "f1", True, "human-reviewer")

    assert first.status == second.status == "confirmed"
    assert JobQueue(db).stats()["total"] == 1


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
