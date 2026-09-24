from pydantic import ValidationError

import app.main as main
import app.orchestrator as orchestrator
from app.htb_lab import (
    HtbLabCampaignInput,
    HtbLabOutcomeInput,
    create_htb_lab_campaign,
    htb_lab_learning_summary,
    record_htb_lab_outcome,
)
from app.storage import Storage


class _FakeQueue:
    def __init__(self):
        self.jobs = {}

    def enqueue(self, campaign_id, kind, payload, *, max_attempts=2, dedupe_key=None):
        job = {
            "id": f"job-{len(self.jobs)+1}",
            "campaign_id": campaign_id,
            "kind": kind,
            "payload": payload,
            "status": "queued",
            "max_attempts": max_attempts,
            "dedupe_key": dedupe_key,
        }
        self.jobs[job["id"]] = job
        return job

    def get(self, job_id):
        return self.jobs.get(job_id)


def test_htb_lab_route_is_exposed():
    assert "/api/labs/htb/campaigns" in main.app.openapi()["paths"]


def test_htb_lab_rejects_public_targets():
    try:
        HtbLabCampaignInput(
            target_url="https://example.com",
            authorized_lab=True,
        )
    except ValidationError as exc:
        assert "exact private IP or a .htb lab hostname" in str(exc)
    else:
        raise AssertionError("public internet targets must be rejected")


def test_htb_lab_requires_explicit_authorization_confirmation():
    try:
        HtbLabCampaignInput(
            target_url="http://10.10.10.10",
            authorized_lab=False,
        )
    except ValidationError as exc:
        assert "authorized_lab must be explicitly true" in str(exc)
    else:
        raise AssertionError("HTB lab confirmation must be explicit")


def test_htb_lab_campaign_is_exact_scope_and_training_only(tmp_path, monkeypatch):
    db = str(tmp_path / "htb.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    result = create_htb_lab_campaign(
        HtbLabCampaignInput(
            target_url="http://10.10.11.42",
            authorized_lab=True,
            name="HTB fixture",
        )
    )

    store = Storage(db, artifacts)
    campaign = store.get_campaign(result["campaign_id"])
    assert campaign is not None
    rules = campaign["target"]["rules"]
    assert rules["allowed_targets"] == ["10.10.11.42"]
    assert rules["denied_targets"] == []
    assert rules["max_requests_per_second"] == 1.0
    assert rules["destructive_testing"] is False
    assert rules["denial_of_service"] is False
    assert rules["social_engineering"] is False
    assert rules["credential_attacks"] is False
    assert result["training_only"] is True
    assert result["automatic_scope_expansion"] is False
    assert any(event.get("type") == "htb_lab_bound" for event in campaign["events"])


def test_htb_lab_start_uses_bounded_planner(tmp_path, monkeypatch):
    db = str(tmp_path / "htb-start.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    created = create_htb_lab_campaign(
        HtbLabCampaignInput(
            target_url="http://10.10.11.43",
            authorized_lab=True,
        )
    )

    fake_queue = _FakeQueue()
    monkeypatch.setattr(main, "queue", lambda: fake_queue)

    calls = []

    def fake_advance(campaign, queue, store):
        calls.append(campaign.id)
        job = queue.enqueue(
            campaign.id,
            "recon_task",
            {"campaign_id": campaign.id, "target": str(campaign.target.primary_url)},
            max_attempts=2,
            dedupe_key="htb-start-fixture",
        )
        return {
            "action": {
                "kind": "crawl",
                "target": str(campaign.target.primary_url),
                "reason": "bounded HTB recon",
                "priority": 100,
            },
            "job_ids": [job["id"]],
        }

    monkeypatch.setattr(orchestrator, "advance_campaign", fake_advance)

    result = main.start_campaign(created["campaign_id"])

    assert calls == [created["campaign_id"]]
    assert result["state"] == "running"
    assert result["job"]["kind"] == "recon_task"
    assert result["planner"]["job_ids"] == [result["job"]["id"]]


def test_htb_outcome_feedback_becomes_learning_memory(tmp_path, monkeypatch):
    db = str(tmp_path / "htb-learning.sqlite3")
    artifacts = str(tmp_path / "artifacts")
    monkeypatch.setenv("XBOW_DB_PATH", db)
    monkeypatch.setenv("XBOW_ARTIFACT_ROOT", artifacts)

    created = create_htb_lab_campaign(
        HtbLabCampaignInput(
            target_url="http://10.10.11.44",
            authorized_lab=True,
        )
    )

    recorded = record_htb_lab_outcome(
        created["campaign_id"],
        HtbLabOutcomeInput(
            solved=True,
            successful_techniques=["web-enumeration", "idor-check"],
            missed_techniques=["graphql-mapping"],
            notes="Operator notes are intentionally not persisted.",
        ),
    )

    assert recorded["training_only"] is True
    assert recorded["learning_observations_written"] == 3
    assert recorded["notes_stored"] is False
    assert recorded["contains_exploit_payloads"] is False

    summary = htb_lab_learning_summary(created["campaign_id"])
    by_technique = {item["technique"]: item for item in summary["techniques"]}
    assert by_technique["web-enumeration"]["successes"] == 1
    assert by_technique["idor-check"]["successes"] == 1
    assert by_technique["graphql-mapping"]["failures"] == 1
    assert summary["scope_expansion"] is False
    assert summary["outcomes"][-1]["solved"] is True
    assert summary["outcomes"][-1]["notes_present"] is True
    assert "notes" not in summary["outcomes"][-1]


def test_htb_outcome_rejects_overlapping_techniques():
    try:
        HtbLabOutcomeInput(
            solved=False,
            successful_techniques=["recon"],
            missed_techniques=["recon"],
        )
    except ValidationError as exc:
        assert "cannot be both successful and missed" in str(exc)
    else:
        raise AssertionError("overlapping technique outcome must be rejected")


def test_htb_learning_routes_are_exposed():
    paths = main.app.openapi()["paths"]
    assert "/api/labs/htb/campaigns/{campaign_id}/outcome" in paths
    assert "/api/labs/htb/campaigns/{campaign_id}/learning" in paths
