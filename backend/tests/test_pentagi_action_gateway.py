import pytest

from app.main import Campaign, CampaignState, ProgramRules, TargetInput
from app.pentagi_action_gateway import (
    PentagiActionGatewayError,
    PentagiFlowBinding,
    authorize_pentagi_action,
)
from app.pentagi_adapter import build_pentagi_flow_plan
from app.pentagi_admission import evaluate_pentagi_admission
from app.storage import Storage


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
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    plan = build_pentagi_flow_plan(
        campaign,
        base_url="https://pentagi.example.test",
        model_provider="openai",
    )
    execution_plan = plan.__class__(
        endpoint=plan.endpoint,
        payload=plan.payload,
        target=plan.target,
        model_provider=plan.model_provider,
        dry_run=False,
        execution_supported=True,
    )
    decision = evaluate_pentagi_admission(campaign, execution_plan)
    assert decision.allowed
    return PentagiFlowBinding(
        flow_id="flow-123",
        campaign_id=campaign.id,
        policy_fingerprint=decision.policy_fingerprint,
        endpoint=execution_plan.endpoint,
        model_provider=execution_plan.model_provider,
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
    other = campaign.model_copy(update={"id": "other"})
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


def test_gateway_rejects_binding_transport_change(monkeypatch):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    tampered = PentagiFlowBinding(
        flow_id=binding.flow_id,
        campaign_id=binding.campaign_id,
        policy_fingerprint=binding.policy_fingerprint,
        endpoint="https://other.example.test/api/v1/graphql",
        model_provider=binding.model_provider,
    )
    with pytest.raises(PentagiActionGatewayError, match="policy"):
        authorize_pentagi_action(
            tampered, campaign, kind="request_recon",
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


def test_storage_persists_and_loads_pentagi_flow_binding(monkeypatch, tmp_path):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    store = Storage(str(tmp_path / "xbow.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(campaign.model_dump(mode="json"))

    stored = store.put_pentagi_flow_binding(
        {
            "flow_id": binding.flow_id,
            "campaign_id": binding.campaign_id,
            "policy_fingerprint": binding.policy_fingerprint,
            "endpoint": binding.endpoint,
            "model_provider": binding.model_provider,
        }
    )

    assert stored["flow_id"] == binding.flow_id
    assert store.get_pentagi_flow_binding(binding.flow_id) == stored


def test_storage_rejects_pentagi_flow_rebinding(monkeypatch, tmp_path):
    campaign = _campaign()
    binding = _binding(monkeypatch, campaign)
    store = Storage(str(tmp_path / "xbow.sqlite3"), str(tmp_path / "artifacts"))
    store.save_campaign(campaign.model_dump(mode="json"))
    store.put_pentagi_flow_binding(
        {
            "flow_id": binding.flow_id,
            "campaign_id": binding.campaign_id,
            "policy_fingerprint": binding.policy_fingerprint,
            "endpoint": binding.endpoint,
            "model_provider": binding.model_provider,
        }
    )

    other = campaign.model_copy(update={"id": "campaign-other"})
    store.save_campaign(other.model_dump(mode="json"))
    with pytest.raises(ValueError, match="flow binding conflict"):
        store.put_pentagi_flow_binding(
            {
                "flow_id": binding.flow_id,
                "campaign_id": other.id,
                "policy_fingerprint": binding.policy_fingerprint,
                "endpoint": binding.endpoint,
                "model_provider": binding.model_provider,
            }
        )
