from dataclasses import replace

import pytest

from app.jobqueue import JobQueue
from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_adapter import build_pentagi_flow_plan
from app.pentagi_dispatch import enqueue_pentagi_flow
from app.pentagi_transport import PentagiTransportError, PentagiTransportResponse
from app.pentagi_worker_service import (
    PentagiWorkerPolicyError,
    _require_worker_runtime,
    pentagi_worker_available,
    preflight_pentagi_job,
    process_one,
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


def _enable_worker(monkeypatch):
    _enable_admission(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")


class _Store:
    def __init__(self, campaign):
        self.campaign = campaign
        self.artifacts = []

    def get_campaign_record(self, campaign_id):
        if campaign_id != self.campaign.id:
            return None
        return self.campaign.model_dump(mode="json"), 1

    def put_artifact(self, campaign_id, kind, content, **kwargs):
        record = {
            "campaign_id": campaign_id,
            "kind": kind,
            "content": content,
            **kwargs,
        }
        self.artifacts.append(record)
        return record


def test_transport_gate_is_explicit(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_PENTAGI_TRANSPORT", raising=False)
    assert pentagi_worker_available() is False
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_TRANSPORT", "true")
    assert pentagi_worker_available() is True


def test_worker_runtime_gate_blocks_before_claim(monkeypatch):
    _enable_admission(monkeypatch)
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI_WORKER", "true")
    monkeypatch.delenv("XBOW_ENABLE_PENTAGI_TRANSPORT", raising=False)

    with pytest.raises(PentagiWorkerPolicyError, match="transport is disabled"):
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


def test_process_one_submits_once_and_completes(tmp_path, monkeypatch):
    _enable_worker(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    job = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
    calls = []

    def submit(plan, permit):
        calls.append((plan, permit))
        return PentagiTransportResponse(
            status=200,
            body={"data": {"createFlow": {"id": "flow-42", "status": "created"}}},
        )

    monkeypatch.setattr("app.pentagi_worker_service.submit_pentagi_flow", submit)

    store = _Store(campaign)
    assert process_one(queue, store, "pentagi-worker") is True
    assert len(calls) == 1
    assert len(store.artifacts) == 1
    receipt = store.artifacts[0]
    assert receipt["kind"] == "pentagi_receipt"
    assert receipt["media_type"] == "application/json"
    decoded = __import__("json").loads(receipt["content"].decode("utf-8"))
    assert decoded["flow_id"] == "flow-42"
    assert decoded["job_id"] == job["id"]
    assert "token" not in decoded
    assert "request" not in decoded
    completed = queue.get(job["id"])
    assert completed["status"] == "completed"
    assert completed["attempts"] == 1


def test_process_one_transport_failure_is_terminal_without_retry(tmp_path, monkeypatch):
    _enable_worker(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    job = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))

    def fail(plan, permit):
        raise PentagiTransportError("connection outcome ambiguous")

    monkeypatch.setattr("app.pentagi_worker_service.submit_pentagi_flow", fail)

    assert process_one(queue, _Store(campaign), "pentagi-worker") is True
    failed = queue.get(job["id"])
    assert failed["status"] == "failed"
    assert failed["attempts"] == 1
    assert queue.claim_kind("pentagi-worker-2", "pentagi_flow") is None


def test_process_one_revalidates_after_claim_before_transport(tmp_path, monkeypatch):
    _enable_worker(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    job = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))

    class _DriftingStore(_Store):
        def __init__(self, campaign):
            super().__init__(campaign)
            self.reads = 0

        def get_campaign_record(self, campaign_id):
            self.reads += 1
            if self.reads == 2:
                self.campaign.target.rules.denied_targets.append("private.example.test")
            return super().get_campaign_record(campaign_id)

    called = False

    def submit(plan, permit):
        nonlocal called
        called = True
        return PentagiTransportResponse(
            status=200,
            body={"data": {"createFlow": {"id": "should-not-run"}}},
        )

    monkeypatch.setattr("app.pentagi_worker_service.submit_pentagi_flow", submit)

    assert process_one(queue, _DriftingStore(campaign), "pentagi-worker") is True
    assert called is False
    assert queue.get(job["id"])["status"] == "failed"


def test_process_one_maintains_lease_during_transport(tmp_path, monkeypatch):
    _enable_worker(monkeypatch)
    monkeypatch.setenv("XBOW_JOB_LEASE_SECONDS", "60")
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
    heartbeats = []
    original_heartbeat = queue.heartbeat

    def heartbeat(job_id, worker_id):
        heartbeats.append((job_id, worker_id))
        return original_heartbeat(job_id, worker_id)

    monkeypatch.setattr(queue, "heartbeat", heartbeat)
    monkeypatch.setattr(
        "app.pentagi_worker_service.submit_pentagi_flow",
        lambda plan, permit: PentagiTransportResponse(
            status=200,
            body={"data": {"createFlow": {"id": "flow-heartbeat", "status": "created"}}},
        ),
    )

    assert process_one(queue, _Store(campaign), "pentagi-worker") is True
    assert len(heartbeats) >= 1


def test_process_one_contains_admission_policy_error(tmp_path, monkeypatch):
    _enable_worker(monkeypatch)
    queue = JobQueue(str(tmp_path / "queue.sqlite3"))
    campaign = _campaign()
    job = enqueue_pentagi_flow(queue, campaign, _future_plan(campaign))
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", "not-a-number")

    called = False

    def submit(plan, permit):
        nonlocal called
        called = True
        return PentagiTransportResponse(
            status=200,
            body={"data": {"createFlow": {"id": "should-not-run"}}},
        )

    monkeypatch.setattr("app.pentagi_worker_service.submit_pentagi_flow", submit)

    assert process_one(queue, _Store(campaign), "pentagi-worker") is True
    assert called is False
    assert queue.get(job["id"])["status"] == "failed"
