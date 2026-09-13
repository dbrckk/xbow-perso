from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass

from .main import Campaign, CampaignState
from .pentagi_adapter import PentagiFlowPlan
from .pentagi_execution_guard import (
    PentagiExecutionGuardError,
    PentagiExecutionPermit,
    verify_pentagi_execution_permit,
)
from .pentagi_transport import PentagiTransportError, submit_pentagi_flow
from .queue_backend import QueueBackend, create_queue
from .storage_backend import create_storage


class PentagiWorkerPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiWorkerPreflight:
    campaign: Campaign
    plan: PentagiFlowPlan
    permit: PentagiExecutionPermit


def _enabled(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def pentagi_worker_available() -> bool:
    """Return whether the reviewed PentAGI transport is explicitly enabled."""

    return _enabled("XBOW_ENABLE_PENTAGI_TRANSPORT")


def _require_worker_runtime() -> None:
    if not _enabled("XBOW_ENABLE_PENTAGI"):
        raise PentagiWorkerPolicyError("PentAGI integration is disabled")
    if not _enabled("XBOW_ENABLE_ACTIVE_SCANS"):
        raise PentagiWorkerPolicyError("active scans are disabled")
    if (os.getenv("DRY_RUN", "true") or "").strip().lower() != "false":
        raise PentagiWorkerPolicyError("dry-run mode blocks PentAGI execution")
    if not _enabled("XBOW_ENABLE_PENTAGI_WORKER"):
        raise PentagiWorkerPolicyError("PentAGI worker is disabled")
    if not pentagi_worker_available():
        raise PentagiWorkerPolicyError("PentAGI transport is disabled")


def _payload_object(job: dict) -> dict:
    payload = job.get("payload")
    if not isinstance(payload, dict):
        raise PentagiWorkerPolicyError("PentAGI job payload is invalid")
    return payload


def preflight_pentagi_job(job: dict, campaign: Campaign) -> PentagiWorkerPreflight:
    """Reconstruct and verify the exact admitted plan without network I/O."""

    if job.get("kind") != "pentagi_flow":
        raise PentagiWorkerPolicyError("worker received a non-PentAGI job")
    if job.get("campaign_id") != campaign.id:
        raise PentagiWorkerPolicyError("PentAGI job campaign does not match")
    if campaign.state == CampaignState.cancelled:
        raise PentagiWorkerPolicyError("campaign is cancelled")

    payload = _payload_object(job)
    request = payload.get("request")
    if not isinstance(request, dict):
        raise PentagiWorkerPolicyError("PentAGI request payload is invalid")

    required_strings = {
        key: payload.get(key)
        for key in (
            "campaign_id",
            "target",
            "policy_fingerprint",
            "idempotency_key",
            "endpoint",
            "model_provider",
        )
    }
    if any(not isinstance(value, str) or not value for value in required_strings.values()):
        raise PentagiWorkerPolicyError("PentAGI job metadata is incomplete")
    if required_strings["campaign_id"] != campaign.id:
        raise PentagiWorkerPolicyError("PentAGI payload campaign does not match")
    if job.get("dedupe_key") != required_strings["idempotency_key"]:
        raise PentagiWorkerPolicyError("PentAGI queue identity does not match permit")

    plan = PentagiFlowPlan(
        endpoint=required_strings["endpoint"],
        payload=request,
        target=required_strings["target"],
        model_provider=required_strings["model_provider"],
        dry_run=False,
        execution_supported=True,
    )
    permit = PentagiExecutionPermit(
        campaign_id=campaign.id,
        target=required_strings["target"],
        policy_fingerprint=required_strings["policy_fingerprint"],
        idempotency_key=required_strings["idempotency_key"],
        endpoint=required_strings["endpoint"],
        model_provider=required_strings["model_provider"],
    )

    try:
        verify_pentagi_execution_permit(permit, campaign, plan)
    except PentagiExecutionGuardError as exc:
        raise PentagiWorkerPolicyError("PentAGI execution permit revalidation failed") from exc

    return PentagiWorkerPreflight(campaign=campaign, plan=plan, permit=permit)


def _load_campaign(store, campaign_id: str) -> Campaign:
    record = store.get_campaign_record(campaign_id)
    if not record:
        raise PentagiWorkerPolicyError("campaign not found")
    raw, _version = record
    return Campaign.model_validate(raw)


def process_one(queue: QueueBackend, store, worker_id: str) -> bool:
    """Claim, revalidate, submit once, and finish one PentAGI flow job."""

    _require_worker_runtime()
    job = queue.claim_kind(worker_id, "pentagi_flow")
    if not job:
        return False

    try:
        campaign = _load_campaign(store, job["campaign_id"])
        preflight = preflight_pentagi_job(job, campaign)

        if not queue.heartbeat(job["id"], worker_id):
            raise PentagiWorkerPolicyError("PentAGI job lease was lost before submission")

        # Reload and revalidate immediately before the mutating remote POST. This
        # catches cancellation or policy drift occurring after the initial claim.
        current_campaign = _load_campaign(store, job["campaign_id"])
        preflight = preflight_pentagi_job(job, current_campaign)
        verify_pentagi_execution_permit(
            preflight.permit,
            current_campaign,
            preflight.plan,
        )

        response = submit_pentagi_flow(preflight.plan, preflight.permit)
        create_flow = response.body["data"]["createFlow"]
        flow_id = create_flow["id"]
        remote_status = create_flow.get("status") or "unknown"

        finished = queue.finish(job["id"], worker_id, True)
        if finished is None:
            raise PentagiWorkerPolicyError(
                "PentAGI flow was created but queue ownership was lost before completion"
            )

        # Keep operational output intentionally non-sensitive.
        print(
            f"pentagi_flow_created job_id={job['id']} "
            f"flow_id={flow_id} status={remote_status}"
        )
        return True
    except (PentagiWorkerPolicyError, PentagiExecutionGuardError, PentagiTransportError) as exc:
        queue.finish(job["id"], worker_id, False, str(exc))
        return True


def _poll_seconds() -> float:
    raw = os.getenv("XBOW_PENTAGI_WORKER_POLL_SECONDS", "1")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("XBOW_PENTAGI_WORKER_POLL_SECONDS must be a number") from exc
    if not 0.2 <= value <= 60.0:
        raise ValueError("XBOW_PENTAGI_WORKER_POLL_SECONDS must be between 0.2 and 60")
    return value


def main() -> None:
    _require_worker_runtime()
    queue = create_queue()
    store = create_storage()
    worker_id = os.getenv(
        "XBOW_PENTAGI_WORKER_ID",
        f"pentagi:{socket.gethostname()}:{os.getpid()}",
    )
    poll = _poll_seconds()
    while True:
        worked = process_one(queue, store, worker_id)
        if not worked:
            time.sleep(poll)


if __name__ == "__main__":
    main()
