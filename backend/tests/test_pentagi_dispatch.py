from dataclasses import replace

import pytest

from app.jobqueue import JobQueue
from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_adapter import build_pentagi_flow_plan
from app.pentagi_dispatch import enqueue_pentagi_flow
from app.pentagi_execution_guard import PentagiExecutionGuardError


def _campaign():
    return Campaign(
        id="pentagi-dispatch",
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
                max_requests_per_second=1.0,
            ),
        ),
    )


def _future_plan(campaign):
    return replace(
        build_pentagi_flow_plan(
            campaign,
            base_url="https://pentagi.example.test",
            model_provider="openai",
        ),
        dry_run=False,
        execution_supported=True,
    )


def _enable_runtime(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", "2.0")


def test_dispatch_is_deduplicated_atomically_in_sqlite(tmp_path, monkeypatch):
    _enable_runtime(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    plan = _future_plan(campaign)

    first = enqueue_pentagi_flow(queue, campaign, plan)
    second = enqueue_pentagi_flow(queue, campaign, plan)

    assert first["id"] == second["id"]
    assert first["kind"] == "pentagi_flow"
    assert first["dedupe_key"].startswith("pentagi:")
    assert queue.stats()["total"] == 1
    assert queue.campaign_job_counts(campaign.id)["pentagi_flow"] == 1


def test_dispatch_payload_is_bound_to_permit(tmp_path, monkeypatch):
    _enable_runtime(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    plan = _future_plan(campaign)

    job = enqueue_pentagi_flow(queue, campaign, plan)

    assert job["payload"]["campaign_id"] == campaign.id
    assert job["payload"]["target"] == str(campaign.target.primary_url)
    assert job["payload"]["endpoint"] == plan.endpoint
    assert job["payload"]["model_provider"] == plan.model_provider
    assert job["payload"]["request"] == plan.payload
    assert len(job["payload"]["policy_fingerprint"]) == 64


def test_dispatch_rejects_current_non_executing_plan(tmp_path, monkeypatch):
    _enable_runtime(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    plan = build_pentagi_flow_plan(
        campaign,
        base_url="https://pentagi.example.test",
        model_provider="openai",
    )

    with pytest.raises(PentagiExecutionGuardError, match="permit denied"):
        enqueue_pentagi_flow(queue, campaign, plan)

    assert queue.stats()["total"] == 0


def test_policy_change_creates_new_identity_not_silent_reuse(tmp_path, monkeypatch):
    _enable_runtime(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    first_plan = _future_plan(campaign)
    first = enqueue_pentagi_flow(queue, campaign, first_plan)

    campaign.target.rules.denied_targets.append("private.example.test")
    second_plan = _future_plan(campaign)
    second = enqueue_pentagi_flow(queue, campaign, second_plan)

    assert first["id"] != second["id"]
    assert first["dedupe_key"] != second["dedupe_key"]
    assert queue.stats()["total"] == 2


def test_pentagi_jobs_are_parked_for_generic_workers(tmp_path, monkeypatch):
    _enable_runtime(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    job = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))

    assert job["status"] == "queued"
    assert queue.claim("generic-worker") is None

    parked = queue.get(job["id"])
    assert parked is not None
    assert parked["status"] == "queued"
    assert parked["attempts"] == 0


def test_parked_pentagi_job_does_not_block_other_work(tmp_path, monkeypatch):
    _enable_runtime(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    parked = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
    active = queue.enqueue("other-campaign", "report", {"platform": "generic"})

    claimed = queue.claim("generic-worker")

    assert claimed is not None
    assert claimed["id"] == active["id"]
    assert queue.get(parked["id"])["status"] == "queued"
    assert queue.get(parked["id"])["attempts"] == 0
