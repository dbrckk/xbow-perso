from dataclasses import replace

import pytest

from app.jobqueue import JobQueue
from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_adapter import build_pentagi_flow_plan
from app.pentagi_dispatch import enqueue_pentagi_flow
from app.pentagi_worker_service import (
    PentagiWorkerPolicyError,
    _require_worker_runtime,
    pentagi_worker_available,
    preflight_pentagi_job,
)


def _campaign():
    return Campaign(
        id="pentagi-worker",
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


def _enable_admission(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", "2.0")


def test_worker_build_is_explicitly_non_executing():
    assert pentagi_worker_available() is False


def test_worker_runtime_gate_blocks_before_claim(monkeypatch):
    _enable_admission(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")

    with pytest.raises(PentagiWorkerPolicyError, match="transport is not available"):
        _require_worker_runtime()


def test_preflight_revalidates_exact_queued_permit(tmp_path, monkeypatch):
    _enable_admission(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    queued = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
    claimed = queue.claim_kind("pentagi-worker", "pentagi_flow")

    result = preflight_pentagi_job(claimed, campaign)

    assert result.permit.idempotency_key == queued["dedupe_key"]
    assert result.plan.payload == queued["payload"]["request"]
    assert result.plan.endpoint == queued["payload"]["endpoint"]


def test_preflight_rejects_policy_drift(tmp_path, monkeypatch):
    _enable_admission(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
    claimed = queue.claim_kind("pentagi-worker", "pentagi_flow")

    campaign.target.rules.denied_targets.append("private.example.test")

    with pytest.raises(PentagiWorkerPolicyError, match="revalidation failed"):
        preflight_pentagi_job(claimed, campaign)


def test_preflight_rejects_queue_identity_tampering(tmp_path, monkeypatch):
    _enable_admission(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
    claimed = queue.claim_kind("pentagi-worker", "pentagi_flow")
    claimed["dedupe_key"] = "pentagi:" + "0" * 64

    with pytest.raises(PentagiWorkerPolicyError, match="queue identity"):
        preflight_pentagi_job(claimed, campaign)
