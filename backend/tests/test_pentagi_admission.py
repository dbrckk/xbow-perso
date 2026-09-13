from dataclasses import replace

import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_adapter import PentagiPolicyError, build_pentagi_flow_plan
from app.pentagi_admission import (
    PentagiAdmissionError,
    evaluate_pentagi_admission,
    require_pentagi_admission,
)


def _campaign(*, rps: float = 1.0):
    return Campaign(
        id="pentagi-admission",
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


def _plan(campaign):
    return build_pentagi_flow_plan(
        campaign,
        base_url="https://pentagi.example.test",
        model_provider="openai",
    )


def _enable_runtime(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", "2.0")


def test_admission_is_fail_closed_by_default(monkeypatch):
    monkeypatch.delenv("XBOW_ENABLE_PENTAGI", raising=False)
    monkeypatch.delenv("XBOW_ENABLE_ACTIVE_SCANS", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    campaign = _campaign()

    decision = evaluate_pentagi_admission(campaign, _plan(campaign))

    assert decision.allowed is False
    assert decision.reasons == (
        "pentagi_disabled",
        "active_scans_disabled",
        "global_dry_run",
        "plan_is_dry_run",
        "execution_transport_not_enforceable",
    )
    assert len(decision.policy_fingerprint) == 64


def test_current_adapter_cannot_be_enabled_into_execution(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign()

    decision = evaluate_pentagi_admission(campaign, _plan(campaign))

    assert decision.allowed is False
    assert decision.reasons == (
        "plan_is_dry_run",
        "execution_transport_not_enforceable",
    )
    with pytest.raises(PentagiAdmissionError, match="execution admission denied"):
        require_pentagi_admission(campaign, _plan(campaign))


def test_admission_rejects_campaign_above_local_cap(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign(rps=3.0)
    future_plan = replace(
        _plan(campaign),
        dry_run=False,
        execution_supported=True,
    )

    decision = evaluate_pentagi_admission(campaign, future_plan)

    assert decision.allowed is False
    assert decision.reasons == ("campaign_rps_exceeds_admission_cap",)


def test_future_enforceable_transport_still_requires_every_gate(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign(rps=1.5)
    future_plan = replace(
        _plan(campaign),
        dry_run=False,
        execution_supported=True,
    )

    decision = evaluate_pentagi_admission(campaign, future_plan)

    assert decision.allowed is True
    assert decision.reasons == ()
    assert require_pentagi_admission(campaign, future_plan) == decision


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("XBOW_ENABLE_PENTAGI", "maybe"),
        ("XBOW_ENABLE_ACTIVE_SCANS", "sometimes"),
        ("DRY_RUN", "2"),
    ],
)
def test_invalid_boolean_configuration_fails_closed(monkeypatch, name, value):
    _enable_runtime(monkeypatch)
    monkeypatch.setenv(name, value)
    campaign = _campaign()

    with pytest.raises(PentagiAdmissionError, match="must be a boolean"):
        evaluate_pentagi_admission(campaign, _plan(campaign))


@pytest.mark.parametrize("value", ["not-a-number", "0", "20.1"])
def test_invalid_admission_cap_fails_closed(monkeypatch, value):
    _enable_runtime(monkeypatch)
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", value)
    campaign = _campaign()

    with pytest.raises(PentagiAdmissionError, match="XBOW_PENTAGI_MAX_ADMISSION_RPS"):
        evaluate_pentagi_admission(campaign, _plan(campaign))


def test_plan_target_mismatch_is_rejected(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign()
    plan = replace(_plan(campaign), target="https://other.example.test/")

    with pytest.raises(PentagiPolicyError, match="does not match campaign target"):
        evaluate_pentagi_admission(campaign, plan)


def test_policy_fingerprint_is_stable_and_policy_sensitive(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign()
    plan = _plan(campaign)

    first = evaluate_pentagi_admission(campaign, plan)
    second = evaluate_pentagi_admission(campaign, plan)
    assert first.policy_fingerprint == second.policy_fingerprint

    campaign.target.rules.denied_targets.append("private.example.test")
    changed = evaluate_pentagi_admission(campaign, plan)
    assert changed.policy_fingerprint != first.policy_fingerprint
