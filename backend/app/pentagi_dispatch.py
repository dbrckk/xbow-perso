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


def enqueue_pentagi_flow(
    queue: QueueBackend,
    campaign: Campaign,
    plan: PentagiFlowPlan,
) -> dict:
    """Persist one admitted PentAGI flow request with atomic deduplication.

    The queue is the source of truth for duplicate prevention. SQLite enforces
    uniqueness with an index and Redis uses WATCH/MULTI around its dedupe index.
    This function still performs no external network request.
    """

    permit = issue_pentagi_execution_permit(campaign, plan)
    verify_pentagi_execution_permit(permit, campaign, plan)
    return queue.enqueue(
        campaign.id,
        "pentagi_flow",
        _job_payload(permit, plan),
        max_attempts=2,
        dedupe_key=permit.idempotency_key,
    )
