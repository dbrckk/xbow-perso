from app.campaign_audit import append_campaign_event, verify_campaign_event_chain
from app.main import Campaign, ProgramRules, TargetInput
from app.storage import Storage
from app.worker_audit import verify_worker_audit_chain
from app.worker_service import _append_event_once, _record_worker_outcome


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
    assert outcomes[0]["audit_seq"] == 1
    assert outcomes[0]["previous_worker_hash"] is None
    assert outcomes[0]["worker_hash"]
    assert verify_worker_audit_chain(saved["events"])["valid"] is True
    assert verify_campaign_event_chain(saved["events"])["valid"] is True
    assert verify_campaign_event_chain(saved["events"])["valid"] is True


def test_worker_outcome_audit_detects_tampering(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)
    job = {
        "id": "job-2",
        "campaign_id": campaign.id,
        "kind": "report",
        "attempts": 1,
    }

    assert _record_worker_outcome(store, job, success=True, status="completed")
    saved = store.get_campaign(campaign.id)
    saved["events"][0]["status"] = "failed"

    result = verify_worker_audit_chain(saved["events"])

    assert result["valid"] is False
    assert result["reason"] == "worker outcome hash mismatch"


def test_worker_outcome_audit_links_multiple_events(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = _campaign()
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    for index in range(2):
        job = {
            "id": f"job-{index + 10}",
            "campaign_id": campaign.id,
            "kind": "report",
            "attempts": 1,
        }
        assert _record_worker_outcome(store, job, success=True, status="completed")

    saved = store.get_campaign(campaign.id)
    outcomes = [event for event in saved["events"] if event.get("type") == "worker_outcome"]

    assert outcomes[0]["audit_seq"] == 1
    assert outcomes[1]["audit_seq"] == 2
    assert outcomes[1]["previous_worker_hash"] == outcomes[0]["worker_hash"]
    assert verify_worker_audit_chain(saved["events"])["valid"] is True



def test_worker_outcome_extends_existing_campaign_audit_chain(tmp_path):
    store = Storage(str(tmp_path / "db.sqlite3"), str(tmp_path / "artifacts"))
    campaign = _campaign()
    append_campaign_event(
        campaign.events,
        {
            "type": "campaign_created",
            "at": "2026-09-13T10:00:00+00:00",
        },
    )
    store.save_campaign(campaign.model_dump(mode="json"), expected_version=0)

    job = {
        "id": "job-chain-1",
        "campaign_id": campaign.id,
        "kind": "report",
        "attempts": 1,
    }
    assert _record_worker_outcome(
        store,
        job,
        success=True,
        status="completed",
    ) is True

    saved = store.get_campaign(campaign.id)
    assert [event["type"] for event in saved["events"]] == [
        "campaign_created",
        "worker_outcome",
    ]
    assert saved["events"][1]["previous_event_hash"] == saved["events"][0]["event_hash"]
    assert verify_campaign_event_chain(saved["events"])["valid"] is True
    assert verify_worker_audit_chain(saved["events"])["valid"] is True



def test_worker_event_helper_seals_and_deduplicates_campaign_event():
    campaign = _campaign()
    append_campaign_event(
        campaign.events,
        {"type": "campaign_created", "at": "t1"},
    )
    event = {
        "type": "report_generated",
        "job_id": "job-report-1",
        "artifact_id": "artifact-1",
        "at": "t2",
    }

    _append_event_once(campaign, event)
    _append_event_once(campaign, event)

    assert len(campaign.events) == 2
    assert campaign.events[1]["event_seq"] == 2
    assert campaign.events[1]["previous_event_hash"] == campaign.events[0]["event_hash"]
    assert verify_campaign_event_chain(campaign.events)["valid"] is True
