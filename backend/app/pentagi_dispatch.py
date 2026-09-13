from __future__ import annotations

from .main import Campaign
from .pentagi_adapter import PentagiFlowPlan
from .pentagi_execution_guard import (
    PentagiExecutionPermit,
    issue_pentagi_execution_permit,
    verify_pentagi_execution_permit,
)
from .queue_backend import QueueBackend


def _job_payload(permit: PentagiExecutionPermit, plan: PentagiFlowPlan) -> dict:
    return {
        "campaign_id": permit.campaign_id,
        "target": permit.target,
        "policy_fingerprint": permit.policy_fingerprint,
        "idempotency_key": permit.idempotency_key,
        "endpoint": permit.endpoint,
        "model_provider": permit.model_provider,
        "request": plan.payload,
    }


def prepare_pentagi_execution_permit(
    campaign: Campaign,
    plan: PentagiFlowPlan,
) -> PentagiExecutionPermit:
    """Create and verify the deterministic permit before any queue mutation."""

    permit = issue_pentagi_execution_permit(campaign, plan)
    verify_pentagi_execution_permit(permit, campaign, plan)
    return permit


def enqueue_pentagi_flow(
    queue: QueueBackend,
    campaign: Campaign,
    plan: PentagiFlowPlan,
    *,
    permit: PentagiExecutionPermit | None = None,
) -> dict:
    """Persist one admitted PentAGI flow request with atomic local deduplication.

    PentAGI createFlow is a mutating remote operation and the upstream API has no
    documented server-side idempotency contract in this integration yet.
    Therefore the queue intentionally uses max_attempts=1: an ambiguous transport
    failure must be reconciled manually instead of risking a duplicate remote flow.
    """

    permit = permit or prepare_pentagi_execution_permit(campaign, plan)
    verify_pentagi_execution_permit(permit, campaign, plan)
    return queue.enqueue(
        campaign.id,
        "pentagi_flow",
        _job_payload(permit, plan),
        max_attempts=1,
        dedupe_key=permit.idempotency_key,
    )
