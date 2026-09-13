from dataclasses import replace

import pytest

from app.main import Campaign, ProgramRules, TargetInput
from app.pentagi_adapter import build_pentagi_flow_plan
from app.pentagi_execution_guard import (
    PentagiExecutionGuardError,
    issue_pentagi_execution_permit,
    verify_pentagi_execution_permit,
)


def _campaign():
    return Campaign(
        id="pentagi-guard",
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


def _enable_runtime(monkeypatch):
    monkeypatch.setenv("XBOW_ENABLE_PENTAGI", "true")
    monkeypatch.setenv("XBOW_ENABLE_ACTIVE_SCANS", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("XBOW_PENTAGI_MAX_ADMISSION_RPS", "2.0")


def test_guard_denies_current_non_executing_adapter(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign()
    plan = build_pentagi_flow_plan(
        campaign,
        base_url="https://pentagi.example.test",
        model_provider="openai",
    )

    with pytest.raises(PentagiExecutionGuardError, match="permit denied"):
        issue_pentagi_execution_permit(campaign, plan)


def test_future_enforceable_plan_gets_stable_idempotency_key(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign()
    plan = _future_plan(campaign)

    first = issue_pentagi_execution_permit(campaign, plan)
    second = issue_pentagi_execution_permit(campaign, plan)

    assert first == second
    assert first.idempotency_key.startswith("pentagi:")
    assert len(first.idempotency_key) == len("pentagi:") + 64


def test_policy_change_invalidates_existing_permit(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign()
    plan = _future_plan(campaign)
    permit = issue_pentagi_execution_permit(campaign, plan)

    campaign.target.rules.denied_targets.append("private.example.test")

    with pytest.raises(PentagiExecutionGuardError, match="does not match"):
        verify_pentagi_execution_permit(permit, campaign, plan)


def test_plan_payload_change_invalidates_existing_permit(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign()
    plan = _future_plan(campaign)
    permit = issue_pentagi_execution_permit(campaign, plan)

    changed_payload = dict(plan.payload)
    changed_variables = dict(changed_payload["variables"])
    changed_variables["input"] = changed_variables["input"] + " Extra instruction."
    changed_payload["variables"] = changed_variables
    changed_plan = replace(plan, payload=changed_payload)

    with pytest.raises(PentagiExecutionGuardError, match="does not match"):
        verify_pentagi_execution_permit(permit, campaign, changed_plan)


def test_runtime_gate_change_invalidates_existing_permit(monkeypatch):
    _enable_runtime(monkeypatch)
    campaign = _campaign()
    plan = _future_plan(campaign)
    permit = issue_pentagi_execution_permit(campaign, plan)

    monkeypatch.setenv("DRY_RUN", "true")

    with pytest.raises(PentagiExecutionGuardError, match="no longer admissible"):
        verify_pentagi_execution_permit(permit, campaign, plan)
