from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .main import Campaign
from .pentagi_adapter import PentagiFlowPlan
from .pentagi_admission import (
    PentagiAdmissionDecision,
    PentagiAdmissionError,
    evaluate_pentagi_admission,
)


class PentagiExecutionGuardError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiExecutionPermit:
    campaign_id: str
    target: str
    policy_fingerprint: str
    idempotency_key: str
    endpoint: str
    model_provider: str


def _canonical_plan_payload(plan: PentagiFlowPlan) -> bytes:
    payload = {
        "endpoint": plan.endpoint,
        "target": plan.target,
        "model_provider": plan.model_provider,
        "payload": plan.payload,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def build_pentagi_idempotency_key(
    campaign: Campaign,
    plan: PentagiFlowPlan,
    decision: PentagiAdmissionDecision,
) -> str:
    material = b"\x1f".join(
        [
            campaign.id.encode("utf-8"),
            decision.policy_fingerprint.encode("ascii"),
            hashlib.sha256(_canonical_plan_payload(plan)).hexdigest().encode("ascii"),
        ]
    )
    return "pentagi:" + hashlib.sha256(material).hexdigest()


def issue_pentagi_execution_permit(
    campaign: Campaign,
    plan: PentagiFlowPlan,
) -> PentagiExecutionPermit:
    """Issue a deterministic permit only for an unchanged, admitted plan.

    This module deliberately does not perform any network I/O. A future transport
    must require this permit immediately before submission, then persist the
    idempotency key so retries cannot create duplicate PentAGI flows.
    """

    try:
        decision = evaluate_pentagi_admission(campaign, plan)
    except PentagiAdmissionError as exc:
        raise PentagiExecutionGuardError("PentAGI admission evaluation failed") from exc

    if not decision.allowed:
        raise PentagiExecutionGuardError(
            "PentAGI execution permit denied: " + ",".join(decision.reasons)
        )

    return PentagiExecutionPermit(
        campaign_id=campaign.id,
        target=plan.target,
        policy_fingerprint=decision.policy_fingerprint,
        idempotency_key=build_pentagi_idempotency_key(campaign, plan, decision),
        endpoint=plan.endpoint,
        model_provider=plan.model_provider,
    )


def verify_pentagi_execution_permit(
    permit: PentagiExecutionPermit,
    campaign: Campaign,
    plan: PentagiFlowPlan,
) -> None:
    """Fail closed if policy or request content changed after permit issuance."""

    decision = evaluate_pentagi_admission(campaign, plan)
    if not decision.allowed:
        raise PentagiExecutionGuardError(
            "PentAGI execution permit no longer admissible: " + ",".join(decision.reasons)
        )

    expected = issue_pentagi_execution_permit(campaign, plan)
    if permit != expected:
        raise PentagiExecutionGuardError(
            "PentAGI execution permit does not match current campaign policy and plan"
        )
