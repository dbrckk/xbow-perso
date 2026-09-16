from dataclasses import replace

import pytest

from app.main import Campaign, CampaignState, ProgramRules, TargetInput
from app.pentagi_action_gateway import (
    PentagiActionGatewayError,
    PentagiFlowBinding,
    authorize_pentagi_action,
)
from app.pentagi_adapter import build_pentagi_flow_plan
from app.pentagi_admission import evaluate_pentagi_admission


def _campaign(*, rps=1.0):
    return Campaign(
        id="campaign-bound",
        state=CampaignState.running,
        target=TargetInput(
            name="fixture",
            primary_url="https://app.example.test",
            rules=ProgramRules(
                authorization_reference="AUTH-1",
                allowed_targets=["*.example.test"],
                denied_targets=["admin.example.test"],
                max_requests_per_second=rps,
            ),
        ),
    )


def _binding(monkeypatch, campaign):
    monkeypatch.setenv("XBOW_PENTAGI_CONTROLLED_FUNCTIONS", "true")
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    plan = build_pentagi_flow_plan(
        campaign,
        base_url="https://pentagi.example.test",
        model_provider="openai",
    )
    decision = evaluate_pentagi_admission(campaign, plan)
    assert decision.allowed
    return PentagiFlowBinding(
        flow_id="flow-123",
        campaign_id=campaign.id,
        policy_fingerprint=decision.policy_fingerprint,
    )


def test_gateway_derives_campaign_from_server_binding(monkeypatch):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    action = authorize_pentagi_action(
        binding,
        campaign,
        kind="request_nuclei_scan",
        target="https://api.example.test",
        requested_rps=0.5,
    )
    assert action.campaign_id == campaign.id
    assert action.target == "https://api.example.test"
    assert action.max_requests_per_second == 0.5


def test_gateway_rejects_wrong_campaign_for_binding(monkeypatch):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    other = replace(campaign, id="other")
    with pytest.raises(PentagiActionGatewayError, match="campaign binding"):
        authorize_pentagi_action(
            binding, other, kind="request_recon",
            target="https://app.example.test", requested_rps=0.5,
        )


def test_gateway_rejects_cancelled_campaign(monkeypatch):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    campaign.state = CampaignState.cancelled
    with pytest.raises(PentagiActionGatewayError, match="cancelled"):
        authorize_pentagi_action(
            binding, campaign, kind="request_recon",
            target="https://app.example.test", requested_rps=0.5,
        )


def test_gateway_rejects_policy_change(monkeypatch):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    campaign.target.rules.denied_targets.append("private.example.test")
    with pytest.raises(PentagiActionGatewayError, match="policy"):
        authorize_pentagi_action(
            binding, campaign, kind="request_recon",
            target="https://app.example.test", requested_rps=0.5,
        )


def test_gateway_rejects_out_of_scope_target(monkeypatch):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    with pytest.raises(PentagiActionGatewayError, match="scope"):
        authorize_pentagi_action(
            binding, campaign, kind="request_nuclei_scan",
            target="https://outside.invalid", requested_rps=0.5,
        )


def test_gateway_rejects_rate_above_campaign_cap(monkeypatch):
    campaign = _campaign(rps=1.0)
    binding = _binding(monkeypatch, campaign)
    with pytest.raises(PentagiActionGatewayError, match="rate"):
        authorize_pentagi_action(
            binding, campaign, kind="request_nuclei_scan",
            target="https://api.example.test", requested_rps=1.1,
        )


def test_gateway_rejects_unknown_action(monkeypatch):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    with pytest.raises(PentagiActionGatewayError, match="action"):
        authorize_pentagi_action(
            binding, campaign, kind="shell",
            target="https://app.example.test", requested_rps=0.5,
        )
