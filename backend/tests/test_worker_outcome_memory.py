from app.main import Campaign, ProgramRules, TargetInput
from app.storage import Storage
from app.worker_service import _record_worker_outcome


def _campaign():
    return Campaign(
        id="worker-memory-1",
        target=TargetInput(
            name="fixture",
            primary_url="https://example.test",
            rules=ProgramRules(
                authorization_reference="explicit-test-authorization",
                allowed_targets=["example.test"],
            ),
        ),
    )


def test_record_worker_outcome_is_idempotent_and_payload_free(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    job = {
        "id": "job-1",
        "campaign_id": campaign.id,
        "kind": "report",
        "attempts": 1,
        "payload": {"secret": "never-store-this"},
        "last_error": "also-never-store-this",
    }

    assert _record_worker_outcome(store, job, success=True, status="completed") is True
    assert _record_worker_outcome(store, job, success=True, status="completed") is True

    saved = store.get_campaign(campaign.id)
    outcomes = [event for event in saved["events"] if event.get("type") == "worker_outcome"]
    assert len(outcomes) == 1
    assert outcomes[0]["job_kind"] == "report"
    assert outcomes[0]["status"] == "completed"
    assert "payload" not in outcomes[0]
    assert "last_error" not in outcomes[0]
    assert "never-store-this" not in str(outcomes[0])
