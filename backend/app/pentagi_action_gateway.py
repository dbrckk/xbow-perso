from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .main import Campaign, CampaignState, is_host_allowed
from .pentagi_adapter import build_pentagi_flow_plan
from .pentagi_admission import evaluate_pentagi_admission


class PentagiActionGatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class PentagiFlowBinding:
    flow_id: str
    campaign_id: str
    policy_fingerprint: str


@dataclass(frozen=True)
class PentagiAuthorizedAction:
    campaign_id: str
    kind: str
    target: str
    max_requests_per_second: float


_TARGET_ACTIONS = {"request_recon", "request_nuclei_scan", "request_validation"}


def authorize_pentagi_action(
    binding: PentagiFlowBinding,
    campaign: Campaign,
    *,
    kind: str,
    target: str,
    requested_rps: float,
) -> PentagiAuthorizedAction:
    if kind not in _TARGET_ACTIONS:
        raise PentagiActionGatewayError("PentAGI action is not allowed")
    if binding.campaign_id != campaign.id:
        raise PentagiActionGatewayError("PentAGI campaign binding does not match")
    if campaign.state == CampaignState.cancelled:
        raise PentagiActionGatewayError("campaign is cancelled")

    plan = build_pentagi_flow_plan(campaign)
    decision = evaluate_pentagi_admission(campaign, plan)
    if not decision.allowed:
        raise PentagiActionGatewayError("current campaign policy is not admissible")
    if binding.policy_fingerprint != decision.policy_fingerprint:
        raise PentagiActionGatewayError("campaign policy changed after flow binding")

    parsed = urlparse(target)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username
        or parsed.password
        or not is_host_allowed(
            host,
            campaign.target.rules.allowed_targets,
            campaign.target.rules.denied_targets,
        )
    ):
        raise PentagiActionGatewayError("target is outside campaign scope")

    try:
        rate = float(requested_rps)
    except (TypeError, ValueError) as exc:
        raise PentagiActionGatewayError("requested rate is invalid") from exc
    campaign_cap = float(campaign.target.rules.max_requests_per_second)
    if rate <= 0 or rate > campaign_cap:
        raise PentagiActionGatewayError("requested rate exceeds campaign rate cap")

    return PentagiAuthorizedAction(
        campaign_id=campaign.id,
        kind=kind,
        target=target,
        max_requests_per_second=rate,
    )
